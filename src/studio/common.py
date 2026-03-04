from enum import Enum


class PromptOption(Enum):
    CAMERA_INFO = "@[camera_info]"
    LIGHT_INFO = "@[light_info]"
    PROMPT_REVERSE = "@[prompt_reverse]"
    TODO = ""
