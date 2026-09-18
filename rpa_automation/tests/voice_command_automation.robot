*** Settings ***
Documentation     Jeeni Reader AI — Voice Command automation.
...
...               A real microphone can't be reliably driven inside an
...               automated browser (no physical mic, flaky speech-to-text
...               network calls in CI). So this suite simulates "the user
...               said X" via a JS test hook exposed in reader.html:
...
...                   window.__jeeniTestTriggerVoice('start')
...
...               That hook calls the EXACT SAME function a real voice
...               recognition result would call — so everything AFTER
...               "hearing" the word (start/stop/translate/speed change)
...               is tested for real. Only the microphone step is simulated.

Library           Browser
Library           OperatingSystem

*** Variables ***
${BASE_URL}           http://127.0.0.1:5000
${TEST_FILE_PATH}     ${CURDIR}${/}testdata${/}sample_document.txt

*** Test Cases ***
Upload Document For Voice Command Test
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    ${current_url}=    Get Url
    Should Contain    ${current_url}    file_id=
    Set Suite Variable    ${DOCUMENT_URL}    ${current_url}

Voice Control Toggle Button Works
    [Documentation]    Real UI check — clicking "Enable voice control"
    ...                should flip it into listening mode and back.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=voiceCmdBtn    visible    timeout=10s

    Click    id=voiceCmdBtn
    Wait For Elements State    id=voiceCmdStatus    visible    timeout=5s
    ${status}=    Get Text    id=voiceCmdStatus
    Should Contain    ${status}    Listening
    Log    ✅ Voice control turned ON successfully!

    Click    id=voiceCmdBtn
    ${status2}=    Get Text    id=voiceCmdStatus
    Should Contain    ${status2}    Say
    Log    ✅ Voice control turned OFF successfully!

Saying Start Triggers Read Aloud
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=readPageBtn    visible    timeout=10s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('start')
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Reading...
    Log    ✅ Voice command "start" triggered Read Aloud successfully!

Saying Stop Stops Reading
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=readPageBtn    visible    timeout=10s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('start')
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('stop')
    Wait For Elements State    id=readPageBtn    enabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Read page
    Log    ✅ Voice command "stop" stopped Read Aloud successfully!

Saying Translate To Hindi Translates And Auto-Reads
    [Documentation]    Simulates "translate to hindi" and verifies BOTH
    ...                the translation happened AND that reading started
    ...                automatically afterwards (no manual click needed).
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=docText    visible    timeout=10s

    ${original_text}=    Get Text    id=docText

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('translate to hindi')

    Wait Until Keyword Succeeds    20s    1s
    ...    Text Should Have Changed    ${original_text}

    Wait For Elements State    id=readPageBtn    disabled    timeout=10s
    Log    ✅ Voice command "translate to hindi" translated AND auto-read successfully!

Saying Faster Increases Reading Speed
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=speedSlider    visible    timeout=10s

    ${before}=    Get Property    id=speedSlider    value
    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('faster')
    Sleep    0.5s
    ${after}=    Get Property    id=speedSlider    value

    Should Be True    ${after} > ${before}
    Log    ✅ Voice command "faster" increased speed from ${before} to ${after}!

Saying Slower Decreases Reading Speed
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=speedSlider    visible    timeout=10s

    ${before}=    Get Property    id=speedSlider    value
    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('slower')
    Sleep    0.5s
    ${after}=    Get Property    id=speedSlider    value

    Should Be True    ${after} < ${before}
    Log    ✅ Voice command "slower" decreased speed from ${before} to ${after}!

*** Keywords ***
Text Should Have Changed
    [Arguments]    ${original_text}
    ${current_text}=    Get Text    id=docText
    Should Not Be Equal    ${original_text}    ${current_text}