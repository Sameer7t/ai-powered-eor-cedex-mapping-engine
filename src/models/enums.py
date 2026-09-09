from enum import Enum

class JobCategory(str, Enum):
    NORMAL = "normal"
    PACKAGE_CLEANING = "package_cleaning"
    SHELL_LEAK = "shell_leak"
    CERTIFICATE = "Certificate"
    EXTERNAL_DIRTY_TO_CLEAN = "External_clean"