import unittest
from copy import deepcopy
from pepper.workspace import (build_workspace, attach_supplements, publish_requests,
    publish_research_request_cells, parse_request_values, read_requests,
    read_research_views, REQUEST_HEADERS)
from unittest.mock import Mock


def result():
    return {'asof': '2026-09-21', 'instruments': {'US:TEST': {'market': 'US', 'ticker': 'TEST',
            'asset_class': 'Stock', 'technical': None, 'growth': None, 'swing': {'status': 'DATA_REQUIRED'}}}}


class WorkspaceTests(unittest.TestCase):
    def test_compact_queue_never_reads_legacy_views(self):
        from urllib.parse import unquote
        session = Mock()
        metadata = Mock()
        metadata.json.return_value = {'sheets': [
            {'properties': {'title': '보완입력', 'gridProperties': {'rowCount': 2000}}},
            {'properties': {'title': 'Review_US'}}]}
        cells = Mock()
        cells.json.return_value = {'values': [REQUEST_HEADERS, ['id'] + ['']*9 + ['manual']]}
        session.get.side_effect = [metadata, cells]
        _, rows = read_requests('test-only', session, queue_name='보완입력')
        self.assertEqual(session.get.call_count, 2)
        self.assertTrue(unquote(session.get.call_args.args[0]).endswith("'보완입력'!A4:Q2000"))
        self.assertEqual(rows[0]['input_value'], 'manual')

    def test_compact_queue_missing_fails_closed(self):
        session = Mock()
        session.get.return_value.json.return_value = {'sheets': []}
        with self.assertRaises(ValueError):
            read_requests('test-only', session, queue_name='보완입력')

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
        with self.assertRaises(ValueError):
            parse_request_values([REQUEST_HEADERS, ['']+['orphaned system value']])

    def test_out_of_scope_retains_input(self):
        old = build_workspace(result())['requests']; old[0]['input_value'] = 'keep'
        r = {'asof': '2026-09-21', 'instruments': {}}
        rows = build_workspace(r, old)['requests']
        self.assertEqual(rows[0]['auto_state'], 'OUT_OF_SCOPE')
        self.assertEqual(rows[0]['input_value'], 'keep')

    def test_duplicate_input_ids_rejected_at_read_boundary(self):
        with self.assertRaises(ValueError):
            parse_request_values([REQUEST_HEADERS, ['same'], ['same']])

    def test_invalid_queue_positions_rejected(self):
        for position in (-1, 0, 3, True, 4.5, '5'):
            old = build_workspace(result())['requests'][:1]
            old[0]['_sheet_row'] = position
            with self.subTest(position=position), self.assertRaises(ValueError):
                publish_requests({'sheets': []}, build_workspace(result(), old), old)

    def test_extended_queue_read_preserves_late_input_position(self):
        meta = {'sheets': [{'properties': {'title': 'Data_Requests', 'sheetId': 123,
                'gridProperties': {'rowCount': 3000, 'columnCount': 23}}}]}
        values = [REQUEST_HEADERS] + [[] for _ in range(2000)] + [['late'] + ['']*9 + ['keep']]
        session = Mock()
        response1, response2 = Mock(), Mock()
        response1.json.return_value = meta
        response2.json.return_value = {'values': values}
        session.get.side_effect = [response1, response2]
        _, rows = read_requests('test-only', session)
        self.assertTrue(session.get.call_args.args[0].endswith('A4:Q3000'))
        self.assertEqual(rows[0]['_sheet_row'], 2004)
        self.assertEqual(rows[0]['input_value'], 'keep')

    def test_compact_reader_selects_targets_without_hidden_tabs(self):
        metadata = Mock(); metadata.json.return_value = {'sheets': [
            {'properties': {'title': 'Price_US', 'gridProperties': {'rowCount': 10}}},
            {'properties': {'title': 'Price_KR', 'gridProperties': {'rowCount': 10}}},
            {'properties': {'title': 'Fundamental', 'gridProperties': {'rowCount': 10}}},
            {'properties': {'title': '보완입력', 'gridProperties': {'rowCount': 10}}},
            {'properties': {'title': 'Settings', 'gridProperties': {'rowCount': 10}}}]}
        batch = Mock(); batch.json.return_value = {'valueRanges': [
            {'values': [['Asset Class','Sector','Ticker','Name','현재가\n(GF)','MA50','MA200','52W High','Dist 52W High','RS 1M','RS 3M','RS 6M','RS 12M','Vol Ratio','Setup Score','Status','RSI(14)','현재가 상태','ATR 20D %\n(AV)'],
                        ['Stock','Tech','NVDA','NVIDIA',100,90,80,110,-.1,.1,.2,.3,.4,1.2,80,'WATCH',60,'LIVE',.04],
                        ['Stock','Tech','OTHER','Other',1,1,1,1,0,0,0,0,0,1,1,'WATCH',50,'LIVE',.02]]},
            {'values': [['Asset Class','Sector','Industry','Symbol','Name','현재가\n(GF)','MA50','MA200','52W High','Dist 52W High','RS 1M','RS 3M','RS 6M','RS 12M','Vol Ratio','Setup Score','Status','RSI(14)','현재가 상태','ATR 20D %\n(AV)'],
                        ['Stock','Tech','Memory','660','SK hynix',10,9,8,11,-.1,.1,.2,.3,.4,1,70,'WATCH',55,'LIVE',.05]]},
            {'values': [['Ticker','종목명','ROE (TTM)','PER (TTM)','Forward PER','PBR','EPS 성장 전망\n(향후 3년)','PEG (3Y 참고)','수익성','성장성','가격 부담','종합 점검','자료 기준일','출처 URL','특이사항','분석 구분'],
                        ['NVDA','NVIDIA',1.0,20,15,10,.5,.3,'양호','성장','점검','검토','2026-09-01','https://example.com','','일반']]}
        ]}
        session = Mock(); session.get.side_effect = [metadata, batch]
        instruments = {
            'US:NVDA': {'market':'US','ticker':'NVDA'},
            'KR:000660': {'market':'KR','ticker':'000660'}}
        result = read_research_views('private', session, instruments)
        self.assertEqual([r['ticker'] for r in result['Price_US']], ['NVDA'])
        self.assertEqual([r['ticker'] for r in result['Price_KR']], ['000660'])
        self.assertEqual(len(result['Fundamental']), 1)
        params = session.get.call_args.kwargs['params']
        self.assertFalse(any('Settings' in r for r in params['ranges']))

    def test_compact_publisher_only_writes_a_to_j(self):
        old = build_workspace(result())['requests']
        for i, row in enumerate(old): row['_sheet_row'] = i + 12
        meta = {'sheets': [{'properties': {'title':'보완입력','sheetId':209,
                'gridProperties': {'rowCount':2000,'columnCount':17}}}]}
        requests = publish_research_request_cells(meta, build_workspace(result(), old), old)
        self.assertTrue(requests)
        for request in requests:
            update = request['updateCells']
            self.assertEqual(update['start']['columnIndex'], 0)
            self.assertEqual(len(update['rows'][0]['values']), 10)


if __name__ == '__main__': unittest.main()
