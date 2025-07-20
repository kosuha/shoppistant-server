from enum import Enum

class RANGE_TYPE(Enum):
    GTE = "GTE"
    LTE = "LTE"
    BETWEEN = "BETWEEN"

class AGREE_TYPE(Enum):
    YES = "Y"
    NO = "N"