GLOBAL_SCALE = 1.25


class Const:
    SCALE = GLOBAL_SCALE
    # 通用
    WINDOW_P = (14 * GLOBAL_SCALE, 14 * GLOBAL_SCALE)  # Padding
    WINDOW_R = 15  # Rounding
    WINDOW_BS = 0  # Border Size

    CHILD_P = (8, 8)
    CHILD_R = 15
    CHILD_BS = 0
    CHILD_SB_R = 6
    CHILD_SB_S = 18
    CHILD_SB_P = 6
    CHILD_SB_BG = (0, 0, 0, 0)
    CHILD_SB_GRAB = (40 / 255, 40 / 255, 40 / 255, 1)
    CHILD_SB_GRAB_ACTIVE = (40 / 255, 40 / 255, 40 / 255, 1)
    CHILD_SB_GRAB_HOVERED = (40 / 255, 40 / 255, 40 / 255, 1)

    FRAME_R = 27
    FRAME_P = WINDOW_P

    ITEM_S = WINDOW_P

    POPUP_R = 20  # Rounding
    POPUP_BS = 2

    CELL_P = (6, 6)  # Cell Padding
    GRAB_R = 10  # Grab Rounding

    # COLORS
    WINDOW_BG = (40 / 255, 40 / 255, 40 / 255, 1)
    MODAL_WINDOW_DIM_BG = (0, 0, 0, 0.7)
    FRAME_BG = (56 / 255, 56 / 255, 56 / 255, 1)
    POPUP_BG = WINDOW_BG
    TRANSPARENT = (0, 0, 0, 0)
    CLOSE_BUTTON_NORMAL = (196 / 255, 196 / 255, 196 / 255, 1)
    CLOSE_BUTTON_ACTIVE = (255 / 255, 87 / 255, 51 / 255, 1)
    CLOSE_BUTTON_HOVERED = (67 / 255, 207 / 255, 124 / 255, 1)
    SLIDER_NORMAL = (42 / 255, 130 / 255, 228 / 255, 1)
    SLIDER_ACTIVE = (0 / 255, 200 / 255, 255 / 255, 1)

    DISABLE = (166 / 255, 166 / 255, 166 / 255, 1)
    BUTTON = (56 / 255, 56 / 255, 56 / 255, 1)
    BUTTON_ACTIVE = (67 / 255, 207 / 255, 124 / 255, 1)
    BUTTON_HOVERED = (75 / 255, 75 / 255, 75 / 255, 1)
    BUTTON_SELECTED = BUTTON_ACTIVE
    TEXT = (1, 1, 1, 1)

    # TOP BAR
    TB_WINDOW_R = 33
    TB_FRAME_R = 27

    # LAYER PANEL
    LP_WINDOW_R = 15
    LP_FRAME_R = 33
    LP_WINDOW_P = (26, 26)
    LP_CELL_P = (11 / 2, 11 / 2)

    LP_INDUSTRIAL_BUTTON_ACTIVE = (20 / 255, 20 / 255, 20 / 255, 1)
    LP_INDUSTRIAL_BUTTON_HOVERED = (40 / 255, 40 / 255, 40 / 255, 1)
    LP_INDUSTRIAL_BUTTON_TEXT_ALIGNX = 0.8
    LP_INDUSTRIAL_CELL_P = (6 / 2, 6)

    # LAYER PANEL
    RP_WINDOW_R = 15
    RP_WINDOW_P = (0, 0)
    RP_R_WINDOW_P = (26, 26)
    RP_FRAME_R = 12
    RP_FRAME_INNER_R = 10
    RP_FRAME_P = WINDOW_P
    RP_CHILD_IS = (10, 10)
    RP_CELL_P = (0, 15 / 2)

    RP_L_BOX_BG = (40 / 255, 40 / 255, 40 / 255, 1)
    RP_R_BOX_BG = (56 / 255, 56 / 255, 56 / 255, 1)
    RP_R_BUTTON = (84 / 255, 84 / 255, 84 / 255, 1)
    RP_R_FRAME_BG_HOVERED = (200 / 255, 66 / 255, 66 / 255, 1)
    RP_R_FRAME_BG_ACTIVE = (200 / 255, 66 / 255, 66 / 255, 1)

    # CANVAS BOX
    CB_WINDOW_P = (16, 16)
    CB_WINDOW_R = 30
    CB_FRAME_BS = 0
    CB_FRAME_R = 27
    CB_POPUP_BS = 0
    CB_FRAME_BG = (65 / 255, 65 / 255, 65 / 255, 1)
