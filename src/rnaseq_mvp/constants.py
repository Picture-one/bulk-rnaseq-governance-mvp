from enum import IntEnum

MVP_VERSION = "0.1.0"
NEXTFLOW_VERSION = "25.10.4"
PIPELINE_NAME = "nf-core/rnaseq"
PIPELINE_VERSION = "3.26.0"


class ExitCode(IntEnum):
    OK = 0
    CONFIG = 2
    PREFLIGHT = 3
    PREPARE = 4
    RUN = 5
    VALIDATE = 6
    REVIEW = 7
    PACKAGE = 8
