*** Settings ***
Documentation     Read Aloud (TTS) automation — clicks Read Page and STOP,
...               and actually verifies the UI state changes, instead of
...               logging a success message unconditionally after a click.
Library           Browser
Library           OperatingSystem

*** Variables ***
${BASE_URL}          http://127.0.0.1:5000
${TEST_FILE_PATH}    ${CURDIR}${/}testdata${/}sample_document.txt

*** Test Cases ***
Voice Automation Using Browser TTS
    [Documentation]    Uploads a real document (so there's real text to
    ...                read — filling #docText manually, like the old
    ...                version did, skips the actual upload/extraction
    ...                pipeline entirely and isn't a real test of it).
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s
    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    # --- Read Page should switch the UI into "reading" state ---
    Click    id=readPageBtn
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Reading...
    Log    ✅ Read Aloud started — button correctly shows "Reading...".

    # --- Stop should reset it back ---
    Click    id=stopBtn
    Wait For Elements State    id=readPageBtn    enabled    timeout=5s
    ${label_after_stop}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label_after_stop}    Read page
    Log    ✅ Stop correctly reset the button back to "Read page".

Speed Slider Affects Reading
    [Documentation]    Confirms the speed slider's label updates when
    ...                dragged, which drives the actual TTS rate.
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s
    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    Evaluate JavaScript    id=speedSlider    (el) => { el.value = '1.8'; el.dispatchEvent(new Event('input')); }
    ${label}=    Get Text    id=speedLabel
    Should Contain    ${label}    1.8×
    Log    ✅ Speed slider label correctly reflects the new speed.