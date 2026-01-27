class NonRetryableError(RuntimeError):
    pass

class InvalidPayloadError(NonRetryableError):
    pass
