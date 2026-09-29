#!/usr/bin/env python3

from __future__ import annotations

import copy
import unittest

from validate_receipt import validate_receipt


class ReceiptTests(unittest.TestCase):
    def valid_start(self):
        return {
            "receipt_kind":"start","task":"audit data","mode":"project_readonly","object":"data","action":"audit","route_state":"D0",
            "components":[{"id":"data-main","type":"shared_data","state":"D0"}],"recovery_level":"R0_CONTINUE",
            "route_id":"RT-DATA-AUDIT","routed_modules":["references/modules/data.md"],"artifact_plan":[]
        }

    def test_valid_start(self):
        self.assertEqual(validate_receipt(self.valid_start()), [])

    def test_wrong_route_and_modules_fail(self):
        payload = self.valid_start()
        payload["route_id"] = "RT-DATA-TREAT"
        payload["routed_modules"] = ["references/modules/modeling.md"]
        errors = validate_receipt(payload)
        self.assertTrue(any("route_id" in error for error in errors))
        self.assertTrue(any("routed_modules" in error for error in errors))

    def test_readonly_artifact_plan_fails(self):
        payload = self.valid_start()
        payload["artifact_plan"] = [{"path":"audit.md","artifact_class":"formal","consumer":"user","purpose":"audit","authorization_basis":"none"}]
        self.assertTrue(any("read-only" in error for error in validate_receipt(payload)))

    def test_valid_readonly_end_and_invalid_mutation(self):
        payload = {"receipt_kind":"end","task":"audit","mode":"project_readonly","route_id":"RT-DATA-AUDIT","changed_artifacts":[],"validation":[{"check":"identity","result":"pass"}],"state_changes":[],"open_items":[],"next_action":None}
        self.assertEqual(validate_receipt(payload), [])
        changed = copy.deepcopy(payload)
        changed["changed_artifacts"] = [{"path":"x","artifact_class":"formal","change":"created"}]
        self.assertTrue(any("read-only" in error for error in validate_receipt(changed)))


if __name__ == "__main__":
    unittest.main()
