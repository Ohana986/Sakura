from __future__ import annotations


PET_WINDOW_STYLEHEET = """
#speechBubble {
    background: rgba(255, 232, 241, 220);
    border: 1px solid rgba(238, 172, 200, 158);
    border-radius: 26px;
}
#speakerName {
    color: #d55b91;
    font-size: 13px;
    font-weight: 700;
}
#speechText {
    color: #4b3440;
    font-size: 19px;
    line-height: 1.35;
}
#replyHistoryPanel {
    background: rgba(255, 255, 255, 92);
    border: 1px solid rgba(238, 172, 200, 154);
    border-radius: 17px;
}
#replyHistoryButton {
    background: transparent;
    border: none;
    border-radius: 13px;
    color: #7a3656;
    font-size: 15px;
    font-weight: 900;
}
#replyHistoryButton:hover {
    background: rgba(255, 255, 255, 130);
    color: #b13e73;
}
#replyHistoryButton:disabled {
    background: transparent;
    color: rgba(122, 54, 86, 92);
}
#inputBar {
    background: transparent;
    border: none;
}
#petInput {
    background: rgba(255, 255, 255, 96);
    border: 1px solid rgba(255, 255, 255, 218);
    border-radius: 19px;
    color: #2f2630;
    font-size: 15px;
    font-weight: 700;
    padding: 3px 16px;
    selection-background-color: rgba(213, 91, 145, 92);
}
#petInput:focus {
    background: rgba(255, 255, 255, 132);
    border: 1px solid rgba(213, 91, 145, 210);
}
#petInput:disabled {
    color: rgba(47, 38, 48, 150);
}
#sendButton {
    background: rgba(213, 91, 145, 232);
    border: 1px solid rgba(255, 255, 255, 150);
    border-radius: 16px;
    color: white;
    font-size: 15px;
    font-weight: 800;
    min-width: 68px;
    padding: 4px 14px;
}
#sendButton:hover {
    background: rgba(191, 63, 122, 242);
    border: 1px solid rgba(255, 241, 247, 190);
}
#sendButton:disabled {
    background: rgba(213, 91, 145, 118);
    border: 1px solid rgba(238, 172, 200, 92);
    color: rgba(255, 255, 255, 178);
}
#screenshotButton {
    background: rgba(213, 91, 145, 232);
    border: 1px solid rgba(255, 255, 255, 150);
    border-radius: 16px;
    color: white;
    font-size: 15px;
    font-weight: 800;
    min-width: 58px;
    padding: 4px 12px;
}
#screenshotButton:hover {
    background: rgba(191, 63, 122, 242);
    border: 1px solid rgba(255, 241, 247, 190);
}
#screenshotButton[screenshotAttached="true"] {
    background: rgba(177, 62, 115, 242);
    border: 1px solid rgba(255, 221, 235, 220);
    color: white;
}
#screenshotButton:disabled {
    background: rgba(213, 91, 145, 118);
    border: 1px solid rgba(238, 172, 200, 92);
    color: rgba(255, 255, 255, 178);
}
#confirmActionButton {
    background: rgba(93, 181, 130, 225);
    border: none;
    border-radius: 16px;
    color: white;
    font-size: 15px;
    font-weight: 800;
    min-width: 58px;
    padding: 4px 12px;
}
#cancelActionButton {
    background: rgba(180, 130, 146, 210);
    border: none;
    border-radius: 16px;
    color: white;
    font-size: 15px;
    font-weight: 800;
    min-width: 58px;
    padding: 4px 12px;
}
"""
