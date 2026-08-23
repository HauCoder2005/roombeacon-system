import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd

from analytics.silver.materializer import (
    SilverMaterializer,
    SilverMaterializationError,
    SilverMetadata,
)


class TestSilverMaterializer(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.materializer = SilverMaterializer(output_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _sample_valid_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "source_code": "phongtro123",
                "rental_post_id": 101,
                "source_listing_id": "pt_101",
                "title_raw": "Phòng trọ đẹp Quận 1",
                "url": "https://phongtro123.com/post/101",
                "price_amount": 3500000.0,
                "area_value": 25.0,
                "location_raw": "Quận 1, TP.HCM",
                "latest_observed_at": "2026-08-23 10:00:00",
                "first_observed_at": "2026-08-20 08:00:00",
                "last_observed_at": "2026-08-23 10:00:00",
                "active_days": 3,
            },
            {
                "source_code": "nhatrovn",
                "rental_post_id": 102,
                "source_listing_id": "nv_102",
                "title_raw": "Nhà trọ sạch sẽ Bình Thạnh",
                "url": "https://nhatrovn.vn/post/102",
                "price_amount": 2800000.0,
                "area_value": 20.0,
                "location_raw": "Quận Bình Thạnh, TP.HCM",
                "latest_observed_at": "2026-08-23 11:00:00",
                "first_observed_at": "2026-08-22 09:00:00",
                "last_observed_at": "2026-08-23 11:00:00",
                "active_days": 1,
            }
        ])

    def test_materialization_succeeds(self):
        df = self._sample_valid_dataframe()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df

        meta = self.materializer.materialize(conn=mock_conn)

        self.assertIsInstance(meta, SilverMetadata)
        self.assertEqual(meta.row_count, 2)
        self.assertEqual(meta.unique_listing_count, 2)
        self.assertTrue(self.materializer.output_file.exists())
        self.assertTrue(self.materializer.metadata_file.exists())

    def test_one_row_per_listing_invariant(self):
        df = self._sample_valid_dataframe()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df

        meta = self.materializer.materialize(conn=mock_conn)
        read_df = pd.read_parquet(self.materializer.output_file)

        self.assertEqual(len(read_df), read_df["rental_post_id"].nunique())
        self.assertEqual(len(read_df), meta.row_count)

    def test_duplicate_rental_post_id_rejected(self):
        df_dup = pd.DataFrame([
            {
                "source_code": "phongtro123",
                "rental_post_id": 101,
                "source_listing_id": "pt_101",
                "title_raw": "Phòng trọ A",
                "url": "https://example.com/1",
                "price_amount": 3000000.0,
                "area_value": 20.0,
                "location_raw": "Quận 1",
                "latest_observed_at": "2026-08-23 10:00:00",
            },
            {
                "source_code": "phongtro123",
                "rental_post_id": 101,  # Duplicate!
                "source_listing_id": "pt_101_dup",
                "title_raw": "Phòng trọ A bản sao",
                "url": "https://example.com/2",
                "price_amount": 3200000.0,
                "area_value": 20.0,
                "location_raw": "Quận 1",
                "latest_observed_at": "2026-08-23 11:00:00",
            }
        ])
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df_dup

        with self.assertRaises(SilverMaterializationError) as ctx:
            self.materializer.materialize(conn=mock_conn)
        self.assertIn("Vi phạm tính duy nhất", str(ctx.exception))

    def test_failed_materialization_preserves_previous_snapshot(self):
        # 1. Ghi snapshot ban đầu thành công
        df_valid = self._sample_valid_dataframe()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df_valid
        self.materializer.materialize(conn=mock_conn)

        initial_mtime = self.materializer.output_file.stat().st_mtime
        initial_df = pd.read_parquet(self.materializer.output_file)

        # 2. Lần thứ 2 lỗi do rỗng (0 dòng)
        mock_conn.execute.return_value.df.return_value = pd.DataFrame()
        with self.assertRaises(SilverMaterializationError):
            self.materializer.materialize(conn=mock_conn)

        # 3. Xác nhận file cũ vẫn nguyên vẹn
        self.assertTrue(self.materializer.output_file.exists())
        current_df = pd.read_parquet(self.materializer.output_file)
        self.assertEqual(len(current_df), len(initial_df))
        self.assertFalse(self.materializer.tmp_file.exists())

    def test_metadata_file_generated_and_valid(self):
        df = self._sample_valid_dataframe()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df

        self.materializer.materialize(conn=mock_conn)

        with open(self.materializer.metadata_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["row_count"], 2)
        self.assertEqual(data["unique_listing_count"], 2)
        self.assertEqual(data["source_view"], "v_latest_posts")
        self.assertIn("phongtro123", data["source_distribution"])
        self.assertIn("nhatrovn", data["source_distribution"])
        # Xác nhận không có credentials
        self.assertNotIn("password", str(data).lower())

    def test_parquet_readable_by_pandas(self):
        df = self._sample_valid_dataframe()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df

        self.materializer.materialize(conn=mock_conn)
        df_loaded = pd.read_parquet(self.materializer.output_file)

        self.assertIsInstance(df_loaded, pd.DataFrame)
        self.assertEqual(df_loaded.shape, (2, 12))

    def test_fake_test_data_excluded(self):
        df_fake = self._sample_valid_dataframe()
        df_fake.loc[0, "source_code"] = "fake_test_platform"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.df.return_value = df_fake

        with self.assertRaises(SilverMaterializationError) as ctx:
            self.materializer.materialize(conn=mock_conn)
        self.assertIn("nguồn dữ liệu không hợp lệ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
