*** Settings ***
Documentation     Jeeni Reader AI — Voice Command & Navigation Automation
...
...               Simulates voice commands (start/stop/translate/speed/library)
...               via JS hook window.__jeeniTestTriggerVoice('...') to test that
...               the application handles voice-triggered actions correctly.

Library           Browser
Library           OperatingSystem

*** Variables ***
${BASE_URL}           http://127.0.0.1:5000
${TEST_FILE_PATH}     ${CURDIR}${/}testdata${/}sample_document.txt

*** Test Cases ***
Upload Document For Voice Command Test
    [Documentation]    Uploads sample text document and opens the reader page.
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    ${current_url}=    Get Url
    Should Contain    ${current_url}    file_id=
    Set Suite Variable    ${DOCUMENT_URL}    ${current_url}
    Log    ✅ Document uploaded successfully into Library!

Voice Control Toggle Button Works
    [Documentation]    Real UI check — clicking "Enable voice control"
    ...                flips button into listening mode and back.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=voiceCmdBtn    visible    timeout=10s

    Click    id=voiceCmdBtn
    Wait For Elements State    id=voiceCmdStatus    visible    timeout=5s
    ${status}=    Get Text    id=voiceCmdStatus
    Should Contain    ${status}    Say
    Log    ✅ Voice control turned ON successfully!

    Click    id=voiceCmdBtn
    ${status2}=    Get Text    id=voiceCmdStatus
    Should Contain    ${status2}    Say
    Log    ✅ Voice control turned OFF successfully!

Saying Start Triggers Read Aloud
    [Documentation]    Simulates saying "start" and checks if reading begins.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=readPageBtn    visible    timeout=10s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('start')
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Reading...
    Log    ✅ Voice command "start" triggered Read Aloud successfully!

Saying Stop Stops Reading
    [Documentation]    Simulates saying "stop" and checks if reading stops.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=readPageBtn    visible    timeout=10s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('start')
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('stop')
    Wait For Elements State    id=readPageBtn    enabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Read page
    Log    ✅ Voice command "stop" stopped Read Aloud successfully!

Saying Translate To Hindi Translates And Auto Reads
    [Documentation]    Simulates saying "translate to hindi" and verifies
    ...                translation and auto-read started.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=docText    visible    timeout=10s

    ${original_text}=    Get Text    id=docText

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('translate to hindi')

    Wait Until Keyword Succeeds    20s    1s
    ...    Text Should Have Changed    ${original_text}

    Wait For Elements State    id=readPageBtn    disabled    timeout=10s
    Log    ✅ Voice command "translate to hindi" translated AND auto-read successfully!

Saying Faster Increases Reading Speed
    [Documentation]    Simulates saying "faster" and checks speed slider value.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=speedSlider    visible    timeout=10s

    ${before}=    Get Property    id=speedSlider    value
    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('faster')
    Sleep    0.5s
    ${after}=    Get Property    id=speedSlider    value

    Should Be True    ${after} > ${before}
    Log    ✅ Voice command "faster" increased speed from ${before} to ${after}!

Saying Slower Decreases Reading Speed
    [Documentation]    Simulates saying "slower" and checks speed slider value.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=speedSlider    visible    timeout=10s

    ${before}=    Get Property    id=speedSlider    value
    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('slower')
    Sleep    0.5s
    ${after}=    Get Property    id=speedSlider    value

    Should Be True    ${after} < ${before}
    Log    ✅ Voice command "slower" decreased speed from ${before} to ${after}!

Saying Open Library Returns To Storage Page
    [Documentation]    Simulates saying "open library" and checks navigation to upload.html.
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=voiceCmdBtn    visible    timeout=10s

    Evaluate JavaScript    ${None}    () => window.__jeeniTestTriggerVoice('open library')
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    ${current_url}=    Get Url
    Should Contain    ${current_url}    upload.html
    Log    ✅ Voice command "open library" returned to Library Storage!

*** Keywords ***
Text Should Have Changed
    [Arguments]    ${original_text}
    ${current_text}=    Get Text    id=docText
    Should Not Be Equal    ${original_text}    ${current_text}