"""Business constraints for Mock query capabilities, separate from JSON shape.

Other Skill families may define different validate_request / validate_result
hooks. These fields are not imposed on every registered Skill globally.
"""
from datetime import datetime
import math

SOURCE='mock-fixture-v1'


class BusinessValidationError(ValueError):
    pass


def device_set(payload):
    if ('device_id' in payload) == ('device_ids' in payload):
        raise BusinessValidationError('exactly one device_id or device_ids required')
    ids=[payload['device_id']] if 'device_id' in payload else payload['device_ids']
    if not ids or len(set(ids)) != len(ids):
        raise BusinessValidationError('device set must be nonempty and unique')
    return set(ids)


def timestamp(value):
    try:
        result=datetime.fromisoformat(value)
    except (ValueError,TypeError):
        raise BusinessValidationError('invalid record/query timestamp') from None
    if result.tzinfo is None:
        raise BusinessValidationError('timestamp requires timezone')
    return result


def query_window(payload):
    start=timestamp(payload['start']) if 'start' in payload else None
    end=timestamp(payload['end']) if 'end' in payload else None
    if start and end and start>=end:
        raise BusinessValidationError('query start must precede end')
    return start,end


class MockQueryContract:
    record_kind='mixed'

    def validate_request(self,payload):
        device_set(payload);query_window(payload)

    def validate_result(self,payload,result):
        requested=device_set(payload)
        if device_set(result)!=requested:
            raise BusinessValidationError('output device set differs from input')
        if result.get('is_mock') is not True or result.get('source')!=SOURCE:
            raise BusinessValidationError('untrusted Mock output provenance')
        start,end=query_window(payload)
        for record in result['records']:
            if record.get('device_id') not in requested:
                raise BusinessValidationError('record belongs to unrequested device')
            if record.get('is_mock') is not True or record.get('source')!=SOURCE:
                raise BusinessValidationError('record Mock provenance missing or untrusted')
            measured=timestamp(record.get('timestamp'))
            if start and measured<start or end and measured>=end:
                raise BusinessValidationError('record timestamp outside requested [start,end)')
            alarm=isinstance(record.get('code'),str) and bool(record['code'])
            value=record.get('temperature_c')
            temperature=type(value) in (int,float) and math.isfinite(value)
            if (self.record_kind=='alarm' and not alarm or
                self.record_kind=='temperature' and not temperature or
                self.record_kind=='mixed' and not (alarm or temperature)):
                raise BusinessValidationError('required business record fields missing')
