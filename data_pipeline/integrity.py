import hashlib
from InspectionOS.storage.repositories import encode


def checksum(payload):return hashlib.sha256(encode(payload).encode()).hexdigest()
def verify(payload,expected):return checksum(payload)==expected
