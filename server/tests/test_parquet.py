from contextlib import contextmanager
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from server import minio, parquet


bucket = minio.CachedRenderResultsBucket
key = 'key.par'
minio.ensure_bucket_exists(bucket)


class ParquetTest(unittest.TestCase):
    @contextmanager
    def _file_on_s3(self, relpath):
        path = Path(__file__).parent / 'test_data' / relpath
        try:
            minio.fput_file(bucket, key, path)
            yield
        finally:
            minio.remove(bucket, key)

    def test_read_header_issue_361(self):
        # https://github.com/dask/fastparquet/issues/361
        with self._file_on_s3('fastparquet-issue-361.par'):
            header = parquet.read_header(bucket, key)
            self.assertEqual(header.columns, [])
            self.assertEqual(header.count, 3)

    def test_read_issue_361(self):
        # https://github.com/dask/fastparquet/issues/361
        with self._file_on_s3('fastparquet-issue-361.par'):
            dataframe = parquet.read(bucket, key)
            self.assertEqual(list(dataframe.columns), [])
            self.assertEqual(len(dataframe), 3)

    def test_read_issue_375_uncompressed(self):
        with self._file_on_s3('fastparquet-issue-375.par'):
            with self.assertRaises(parquet.FastparquetIssue375):
                parquet.read(bucket, key)

    def test_read_issue_375_snappy(self):
        with self._file_on_s3('fastparquet-issue-375-snappy.par'):
            with self.assertRaises(parquet.FastparquetIssue375):
                parquet.read(bucket, key)

    def test_na_only_categorical_has_object_dtype(self):
        # Start with a Categorical with no values. (In Workbench, all
        # Categoricals are text.)
        expected = pd.DataFrame({'A': [np.nan]}, dtype=str).astype('category')
        assert expected['A'].cat.categories.dtype == object
        try:
            parquet.write(bucket, key, expected)
            result = parquet.read(bucket, key)
        finally:
            minio.remove(bucket, key)
        assert_frame_equal(result, expected)
