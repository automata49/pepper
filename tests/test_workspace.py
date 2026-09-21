import unittest
from copy import deepcopy
from pepper.workspace import build_workspace, attach_supplements, publish_requests, parse_request_values, REQUEST_HEADERS


def result():
    return {'asof': '2026-09-21', 'instruments': {'US:TEST': {'market': 'US', 'ticker': 'TEST',
            'asset_class': 'Stock', 'technical': None, 'growth': None, 'swing': {'status': 'DATA_REQUIRED'}}}}


class WorkspaceTests(unittest.TestCase):
    def test_stable_requests_and_human_input_preserved(self):
        r = result()
        first = build_workspace(r)['requests']
        first[0]['input_value'] = 'human note'
        second = build_workspace(dict(r, asof='2026-09-22'), first)['requests']
        self.assertEqual(first[0]['request_id'], second[0]['request_id'])
        self.assertEqual(second[0]['input_value'], 'human note')
        self.assertEqual(second[0]['auto_state'], 'SUBMITTED_NOT_VERIFIED')
        self.assertEqual(second[0]['first_seen'], '2026-09-21')
        self.assertEqual(second[0]['last_seen'], '2026-09-22')

    def test_etfs_do_not_receive_roe_requests(self):
        r = result(); r['instruments']['US:TEST']['asset_class'] = 'ETF'
        self.assertEqual([x['field'] for x in build_workspace(r)['requests']], ['price_history'])

    def test_supplement_not_promoted_and_future_source_rejected(self):
        r = result(); previous = build_workspace(r)['requests']
        previous[0].update(input_value='100', source_url='https://example.com/filing', source_date='2026-09-20')
        baseline = deepcopy(r['instruments'])
        attach_supplements(r, previous)
        self.assertEqual(len(r['manual_supplements']), 1)
        self.assertEqual(r['instruments'], baseline)
        previous[0]['source_date'] = '2026-09-22'
        attach_supplements(r, previous)
        self.assertEqual(r['manual_supplements'], [])
        self.assertEqual(len(r['supplement_issues']), 1)

    def test_publisher_never_writes_manual_columns(self):
        r = result(); old = build_workspace(r)['requests']
        for i, row in enumerate(old): row['_sheet_row'] = i+15  # retain holes/user row position
        meta = {'sheets': [{'properties': {'title': 'Data_Requests', 'sheetId': 123,
                'gridProperties': {'rowCount': 2000, 'columnCount': 23}}}]}
        requests = publish_requests(meta, build_workspace(r, old), old)
        writes = [x['updateCells'] for x in requests if 'updateCells' in x and x['updateCells'].get('start', {}).get('sheetId') == 123]
        for write in writes:
            if write['start']['rowIndex'] >= 4:
                self.assertTrue(all(len(row['values']) == 10 for row in write['rows']))
        self.assertTrue(any(x['start']['rowIndex'] == 15 for x in writes))
        self.assertFalse(any('range' in x and x['range'].get('sheetId') == 123 for x in writes))

    def test_duplicate_ids_and_header_drift_rejected(self):
        row = build_workspace(result())['requests'][0]
        with self.assertRaises(ValueError): build_workspace(result(), [row, row])
        with self.assertRaises(ValueError): parse_request_values([['bad header']])
        self.assertEqual(parse_request_values([REQUEST_HEADERS]), [])
        with self.assertRaises(ValueError):
            parse_request_values([REQUEST_HEADERS, ['']*10+['orphaned input']])

    def test_out_of_scope_retains_input(self):
        old = build_workspace(result())['requests']; old[0]['input_value'] = 'keep'
        r = {'asof': '2026-09-21', 'instruments': {}}
        rows = build_workspace(r, old)['requests']
        self.assertEqual(rows[0]['auto_state'], 'OUT_OF_SCOPE')
        self.assertEqual(rows[0]['input_value'], 'keep')


if __name__ == '__main__': unittest.main()
