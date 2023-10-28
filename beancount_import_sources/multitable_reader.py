from typing import List, Optional, Tuple, Dict, Set
import pandas as pd

class MultiTableReader:
    def __init__(self):
        pass

    def _is_section_title(self, row):
        return len(self._drop_trailing_nones(row)) == 1

    def _drop_trailing_nones(self, l: list) -> list:
        while len(l) > 0 and l[-1] is None:
            l.pop()
        return l

    def _get_rows(self, data: list[list[str]], columns: list[str]) -> list[list[str]]:
        result = []
        for row_in in data:
            row_out = []
            for i in range(len(columns)):
                if i < len(row_in):
                    row_out.append(row_in[i])
                else:
                    row_out.append(None)
            result.append(row_out)
        return result

    def read_tables(self, rows: list[list[str]]) -> dict[str, pd.DataFrame]:
        grouped_rows = {}
        cur_table_name = None
        for row in rows:
            if self._is_section_title(row):
                cur_table_name = row[0]
                grouped_rows[cur_table_name] = []
            else:
                grouped_rows[cur_table_name].append(row)

        result = {}
        for table_name, rows in grouped_rows.items():
            if len(rows) == 0:
                df = pd.DataFrame()
            else:
                columns = rows[0]
                data = self._get_rows(data=rows[1:], columns=columns)
                df = pd.DataFrame.from_records(data=data, columns=columns)
            result[table_name] = df
        return result
