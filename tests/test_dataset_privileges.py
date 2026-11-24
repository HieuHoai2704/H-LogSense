"""Least-privilege dataset grant guards; no MySQL connection is made here."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from scripts.run.mysql_runtime import grant_dataset_crud


class DatasetPrivilegeTests(unittest.TestCase):
    def invoke(self, tables=(("datasets",), ("user_datasets",)), *, port=13307):
        cursor = MagicMock()
        cursor.fetchall.return_value = tables
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with (
            patch("scripts.run.mysql_runtime.owned_root", return_value=Path("owned")) as owned,
            patch("scripts.run.mysql_runtime.status", return_value={"port": port}) as status,
            patch("scripts.run.mysql_runtime.load", return_value={"port": 13307}) as load,
            patch("scripts.run.mysql_runtime.connect") as connect,
        ):
            connect.return_value.__enter__.return_value = connection
            result = grant_dataset_crud(".local/owned", "logsense_test_0123456789ab")
        return result, cursor, owned, status, load, connect

    def test_only_two_table_delete_grants_after_existence_check(self):
        result, cursor, owned, status, load, connect = self.invoke()
        statements = [args.args[0] for args in cursor.execute.call_args_list]
        self.assertEqual(
            statements[1:],
            [
                "GRANT DELETE ON `logsense_test_0123456789ab`.`datasets` TO 'logsense_app'@'localhost'",
                "GRANT DELETE ON `logsense_test_0123456789ab`.`user_datasets` TO 'logsense_app'@'localhost'",
            ],
        )
        self.assertEqual(
            cursor.execute.call_args_list[0].args[1],
            ("logsense_test_0123456789ab", "datasets", "user_datasets"),
        )
        self.assertFalse(any(".*" in statement or "GRANT OPTION" in statement for statement in statements))
        self.assertEqual(result["tables_granted"], ["datasets", "user_datasets"])
        self.assertFalse(result["data_deleted"])
        owned.assert_called_once_with(".local/owned")
        status.assert_called_once_with(Path("owned"))
        load.assert_called_once_with(Path("owned"))
        connect.assert_called_once()

    def test_invalid_identifiers_never_read_private_settings_or_connect(self):
        for schema in (
            "",
            "x" * 65,
            "db`.* TO 'other'@'%'",
            "db.name",
            "db-name",
            "db\nname",
            " db",
            None,
            123,
            "école",
        ):
            with (
                self.subTest(schema=schema),
                patch("scripts.run.mysql_runtime.load") as load,
                patch("scripts.run.mysql_runtime.status") as status,
                patch("scripts.run.mysql_runtime.connect") as connect,
            ):
                with self.assertRaises(ValueError):
                    grant_dataset_crud(".local/owned", schema)
                load.assert_not_called()
                status.assert_not_called()
                connect.assert_not_called()

    def test_missing_table_never_partially_grants(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("datasets",)]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with (
            patch("scripts.run.mysql_runtime.owned_root", return_value=Path("owned")),
            patch("scripts.run.mysql_runtime.status", return_value={"port": 13307}),
            patch("scripts.run.mysql_runtime.load", return_value={"port": 13307}),
            patch("scripts.run.mysql_runtime.connect") as connect,
        ):
            connect.return_value.__enter__.return_value = connection
            with self.assertRaisesRegex(ValueError, "migrations"):
                grant_dataset_crud(".local/owned", "logsense_dev")
        self.assertEqual(cursor.execute.call_count, 1)
        self.assertNotIn("GRANT", cursor.execute.call_args.args[0])

    def test_port_mismatch_never_grants(self):
        with (
            patch("scripts.run.mysql_runtime.owned_root", return_value=Path("owned")),
            patch("scripts.run.mysql_runtime.status", return_value={"port": 13306}),
            patch("scripts.run.mysql_runtime.load", return_value={"port": 13307}),
            patch("scripts.run.mysql_runtime.connect") as connect,
        ):
            with self.assertRaisesRegex(ValueError, "port"):
                grant_dataset_crud(".local/owned", "logsense_dev")
            connect.assert_not_called()

    def test_ownership_failure_never_opens_grant_connection(self):
        with (
            patch("scripts.run.mysql_runtime.owned_root", return_value=Path("owned")),
            patch("scripts.run.mysql_runtime.status", side_effect=ValueError("Ownership mismatch")),
            patch("scripts.run.mysql_runtime.load") as load,
            patch("scripts.run.mysql_runtime.connect") as connect,
        ):
            with self.assertRaisesRegex(ValueError, "Ownership"):
                grant_dataset_crud(".local/owned", "logsense_dev")
            load.assert_not_called()
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
