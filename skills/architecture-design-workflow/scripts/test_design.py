"""Behavioral tests using synthetic office and outdoor-study fixtures."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from design_site import earthwork, positive_volume, routes
from project_state import add_revision, new_project, set_status, validate_state

ROOT = Path(__file__).resolve().parent.parent
OFFICE = ROOT / "assets" / "office-study.json"
SITE = ROOT / "assets" / "site-study.json"


def fixture(path):
    return json.loads(path.read_text(encoding="utf-8"))


def square(x, y, width, depth):
    return {"type": "Polygon", "coordinates": [[[x, y], [x+width, y], [x+width, y+depth],
                                                [x, y+depth], [x, y]]]}


@unittest.skipUnless(importlib.util.find_spec("shapely"), "Shapely geometry dependency unavailable")
class GeometryTests(unittest.TestCase):
    def setUp(self):
        from design_geometry import evaluate, shell_output
        self.evaluate = evaluate
        self.shell = shell_output
        self.data = fixture(OFFICE)

    def test_office_acceptance_uses_room_nets_and_plate_gross(self):
        result = self.evaluate(self.data, "accept")
        self.assertTrue(result["passed"], result["issues"])
        self.assertEqual(result["area_m2"]["gross"], 184)
        self.assertAlmostEqual(result["area_m2"]["net_total"], 168.68)
        self.assertAlmostEqual(result["area_m2"]["net/vertical"], 43.68)
        self.assertAlmostEqual(result["area_m2"]["estimated_room_enclosure"], 15.32)
        self.assertEqual(result["levels"]["L1"]["unexplained_m2"], 0)
        self.assertTrue(result["manual"])

    def test_shell_is_independent_and_void_is_level_specific(self):
        before = self.shell(self.data)
        self.data["rooms"] = [{"anything": "even an incomplete layout cannot change the shell"}]
        self.assertEqual(before, self.shell(self.data))
        self.assertEqual(before["levels"]["L0"]["gross_m2"], 96)
        self.assertEqual(before["levels"]["L1"]["gross_m2"], 88)
        slab = before["meshes"]["level/L1"][0]
        self.assertTrue(all(len(v) == 3 for v in slab["vertices_m"]))

    def test_roof_cut_and_nonorthogonal_mass_meshes_are_closed(self):
        self.data["masses"] = [{"id": "diagonal", "z_range_m": [0, 2],
                               "polygon": {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [2, 2], [0, 0]]]}}]
        outputs = self.shell(self.data)["meshes"]
        for name in ("roof/west", "mass/diagonal"):
            mesh = outputs[name][0]
            edges = Counter()
            for face in mesh["faces"]:
                edges.update(tuple(sorted(pair)) for pair in zip(face, face[1:]+face[:1]))
            self.assertTrue(all(degree == 2 for degree in edges.values()))
        self.assertGreater(
            max(v[2] for v in outputs["roof/west"][0]["vertices_m"]),
            min(v[2] for v in outputs["roof/west"][0]["vertices_m"]),
        )

    def test_budget_violations_are_visible_during_exploration_and_block_acceptance(self):
        self.data["area_limits_m2"]["net/vertical"]["max"] = 30
        self.data["room_requirements"][0]["budget"].update(min=29, target=29)
        explore = self.evaluate(self.data, "explore")
        strict = self.evaluate(self.data, "accept")
        self.assertTrue(explore["passed"])
        self.assertFalse(explore["declared_checks_clear"])
        self.assertFalse(strict["passed"])
        self.assertEqual({i["id"] for i in strict["issues"] if i["code"] == "budget"},
                         {"work", "net/vertical"})
        self.assertTrue(all(i["severity"] == "warning" for i in explore["issues"]))

    def test_unknown_categories_cannot_silently_pass_area_caps(self):
        self.data["area_limits_m2"]["net/storage"] = {"max": 12}
        with self.assertRaisesRegex(ValueError, "Unknown area metric net/storage"):
            self.evaluate(self.data, "accept")
        self.data["categories"] = ["storage"]
        self.assertEqual(self.evaluate(self.data, "accept")["checks"]["net/storage"]["measured_m2"], 0)

    def test_missing_program_room_and_untallied_space_are_reported(self):
        self.data["rooms"].pop(1)
        result = self.evaluate(self.data, "accept")
        self.assertTrue({"missing_room", "unexplained_area"} <= {i["code"] for i in result["issues"]})
        self.assertAlmostEqual(result["levels"]["L0"]["unexplained_m2"], 30)

    def test_bow_tie_zero_area_and_dissolved_net_never_count(self):
        self.data["rooms"][0]["polygon"] = square(0, 0, 0, 8)
        self.data["rooms"][1]["polygon"] = {"type": "Polygon", "coordinates":
                                          [[[0, 1], [6, 6], [0, 6], [5, 1], [0, 1]]]}
        self.data["rooms"][2]["net_inset_m"] = 2
        result = self.evaluate(self.data, "explore")
        invalid = {i["id"] for i in result["issues"] if i["code"] == "invalid_geometry"}
        self.assertEqual(invalid, {"lobby", "work", "corr"})

    def test_room_outside_after_length_tolerance_and_unclosed_ring_fail(self):
        self.data["rooms"][0]["polygon"] = square(-.1, 0, 6.1, 3)
        self.data["rooms"][1]["polygon"]["coordinates"][0].pop()
        result = self.evaluate(self.data, "accept")
        self.assertIn(("lobby", "outside_plate"), {(i["id"], i["code"]) for i in result["issues"]})
        self.assertIn(("work", "invalid_geometry"), {(i["id"], i["code"]) for i in result["issues"]})

    def test_room_overlap_is_detected_without_double_counting_occupied_area(self):
        self.data["rooms"][1]["polygon"] = square(0, 2, 6, 6)
        result = self.evaluate(self.data, "accept")
        self.assertIn("overlap", {i["code"] for i in result["issues"]})
        self.assertEqual(result["levels"]["L0"]["occupied_outline_m2"], 96)
        self.assertEqual(result["area_m2"]["outline_total"], 190)

    def test_clipped_room_and_probe_are_checked(self):
        self.data["rooms"][1]["candidate_polygon"] = square(0, 3, 8, 5)
        self.data["room_requirements"][0]["budget"].update(max_loss_m2=5, min_width_m=5)
        result = self.evaluate(self.data, "accept")
        self.assertTrue({"clipped_room", "size", "narrow"} <= {i["code"] for i in result["issues"]})

    def test_cut_driven_candidate_does_not_change_plate_or_source(self):
        from design_geometry import adapt_candidate, polygon, read_shell
        plate = read_shell(self.data)["L1"][0]
        room = polygon(square(6, 0, 3, 8), "candidate")
        available, removed = adapt_candidate(room, plate)
        self.assertEqual(removed, 8)
        self.assertEqual(available.area, 16)
        self.assertEqual(room.area, 24)
        self.assertEqual(plate.area, 88)

    def test_invalid_opening_and_wrong_level_leave_destinations_unreachable(self):
        changed = self.data["connections"][1]
        changed["segment"] = [[1, 2], [2.2, 2]]
        self.data["connections"][-1]["to_xyz"][2] = 4.1
        result = self.evaluate(self.data, "accept")
        seen = {(i["code"], i["id"]) for i in result["issues"]}
        self.assertIn(("door_opening", "office-door"), seen)
        self.assertIn(("required_opening", "work"), seen)
        self.assertIn(("vertical_connection", "landings"), seen)
        self.assertIn(("unreachable", "upper-work"), seen)

    def test_explained_structure_cannot_overlap_rooms(self):
        self.data["explained_areas"] = [{"level": "L0", "polygon": square(0, 0, 1, 1),
                                          "category": "structure", "reason": "fixture"}]
        result = self.evaluate(self.data, "accept")
        self.assertIn("explained_area_overlap", {i["code"] for i in result["issues"]})

    def test_outdoor_area_is_separate_from_gross(self):
        self.data["outdoor_areas"] = [{"id": "garden", "polygon": square(0, -2, 3, 2)}]
        result = self.evaluate(self.data, "accept")
        self.assertEqual(result["area_m2"]["outdoor_total"], 6)
        self.assertEqual(result["area_m2"]["gross"], 184)


class StageTests(unittest.TestCase):
    def test_revision_advances_by_stage_and_revisiting_history_keeps_lineage(self):
        state = new_project(["concept", "develop"])
        prep = add_revision(state, "concept", "first")
        add_revision(state, "concept", "revised")
        with self.assertRaisesRegex(ValueError, "approval basis"):
            add_revision(state, "develop", "detail")
        approval = {"by": "user", "basis": "select concept for detailing"}
        third = add_revision(state, "develop", "detail", approval=approval)
        with self.assertRaises(ValueError):
            add_revision(state, "develop", "use original", source=prep["id"])
        restored = add_revision(state, "develop", "use original", source=prep["id"], approval=approval)
        self.assertEqual(third["id"], "develop/V1")
        self.assertEqual(restored["id"], "develop/V2")
        self.assertEqual(restored["source"], "concept/V1")
        self.assertEqual(restored["parent"], "develop/V1")
        validate_state(state)

    def test_pause_blocks_revisions_until_approval_to_resume(self):
        state = new_project(["concept"])
        add_revision(state, "concept", "first")
        set_status(state, "paused", "await review")
        with self.assertRaisesRegex(ValueError, "paused"):
            add_revision(state, "concept", "attempt")
        with self.assertRaises(ValueError):
            set_status(state, "active", "attempt")
        set_status(state, "active", "review supplied", {"by": "user", "basis": "feedback received"})
        add_revision(state, "concept", "after feedback")
        validate_state(state)
        bad = deepcopy(state)
        bad["status_history"][1]["after_revisions"] = 2
        with self.assertRaisesRegex(ValueError, "paused"):
            validate_state(bad)

    def test_existing_artifact_path_is_not_reused(self):
        state = new_project(["study"])
        add_revision(state, "study", "first", artifacts=["study/v1.blend"])
        with self.assertRaisesRegex(ValueError, "unique"):
            add_revision(state, "study", "attempt", artifacts=["study/./v1.blend"])

    def test_cli_failure_preserves_state_file_and_releases_lock(self):
        script = ROOT/"scripts/project_state.py"
        with TemporaryDirectory() as folder:
            path = Path(folder)/"project.json"
            subprocess.run([sys.executable, str(script), str(path), "init", "study", "detail"],
                           check=True, capture_output=True)
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(script), str(path), "record", "detail", "--note", "try"],
                                    capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name(path.name+".lock").exists())


class SiteTests(unittest.TestCase):
    def test_mixed_sign_triangle_and_material_conversion(self):
        result = earthwork(fixture(SITE)["earthwork"])
        self.assertAlmostEqual(result["cut_m3_bank"], 1/6)
        self.assertAlmostEqual(result["geometric_fill_m3"], 5/6)
        case = result["material_cases"]["assumed"]
        self.assertAlmostEqual(case["available_m3_compacted"], .12)
        self.assertAlmostEqual(case["balance_m3_compacted"], .12 - 5/6 - .1)

    def test_triangle_integral_all_fill_zero_or_symmetric(self):
        self.assertEqual(positive_volume(3, [3, 3, 3]), 9)
        self.assertEqual(positive_volume(3, [0, -1, -5]), 0)
        self.assertEqual(positive_volume(3, [-2, 0, 0]), 0)
        self.assertEqual(positive_volume(3, [0, 0, 0]), 0)
        self.assertAlmostEqual(positive_volume(4, [1, -1, 0]), 2/3)

    def test_duplicate_or_degenerate_triangles_fail(self):
        data = fixture(SITE)["earthwork"]
        data["triangles"].append([2, 1, 0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            earthwork(data)
        data["triangles"] = [[0, 0, 1]]
        with self.assertRaisesRegex(ValueError, "indices"):
            earthwork(data)

    def test_grade_and_valid_directed_return(self):
        data = fixture(SITE)["paths"]
        result = routes(data)
        self.assertTrue(result["passed"])
        self.assertEqual(result["routes"]["arrival_path"]["peak_absolute_grade_pct"], 4)
        self.assertIsNone(result["routes"]["elevator"]["segments"][0]["grade_pct"])
        data["routes"][0]["direction"] = "forward"
        data["routes"][0]["max_grade_pct"] = 3.9
        result = routes(data)
        self.assertEqual({i["code"] for i in result["issues"]}, {"grade", "return_missing"})

    def test_disconnected_join_reports_z_mismatch(self):
        data = fixture(SITE)["paths"]
        data["nodes"].append({"id": "other", "xyz": [10, 0, .5]})
        data["joins"] = [["garden", "other"]]
        self.assertEqual(routes(data)["issues"][0]["code"], "join_gap")


if __name__ == "__main__":
    unittest.main(verbosity=2)
