*** Settings ***
Documentation     Jeeni Reader AI — Translate Page automation.
...               Uploads a document, opens the reader, selects a target
...               language, clicks Translate, and verifies the on-screen
...               text actually changes (i.e. /translate round-trip worked).

Library           Browser
Library           OperatingSystem

*** Variables ***
${BASE_URL}           http://127.0.0.1:5000
${TEST_FILE_PATH}     ${CURDIR}${/}testdata${/}sample_document.txt

*** Test Cases ***
Upload Document For Translation Test
    [Documentation]    Uploads a fresh document and lands on the reader,
    ...                so this suite doesn't depend on a document already
    ...                being open from another test file.
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    ${current_url}=    Get Url
    Should Contain    ${current_url}    file_id=
    Set Suite Variable    ${DOCUMENT_URL}    ${current_url}

Translate Page To Hindi Changes The Text
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=translateBtn    visible    timeout=10s

    ${original_text}=    Get Text    id=docText

    Select Options By    id=langSelect    value    hi
    Click    id=translateBtn

    Wait For Elements State    id=translateBtn    enabled    timeout=20s
    ${translated_text}=    Get Text    id=docText
    Should Not Be Equal    ${original_text}    ${translated_text}
    Log    ✅ Translated to Hindi successfully!

Translate Page To Gujarati Changes The Text
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=translateBtn    visible    timeout=10s

    ${original_text}=    Get Text    id=docText

    Select Options By    id=langSelect    value    gu
    Click    id=translateBtn

    Wait For Elements State    id=translateBtn    enabled    timeout=20s
    ${translated_text}=    Get Text    id=docText
    Should Not Be Equal    ${original_text}    ${translated_text}
    Log    ✅ Translated to Gujarati successfully!

Translated Text Can Still Be Read Aloud
    [Documentation]    After translating, clicking Read Page should read
    ...                the TRANSLATED text (not the original).
    New Page    ${DOCUMENT_URL}
    Wait For Elements State    id=translateBtn    visible    timeout=10s

    Select Options By    id=langSelect    value    hi
    Click    id=translateBtn
    Wait For Elements State    id=translateBtn    enabled    timeout=20s

    Click    id=readPageBtn
    Wait For Elements State    id=readPageBtn    disabled    timeout=5s
    ${label}=    Get Text    id=readBtnLabel
    Should Be Equal    ${label}    Reading...

    Click    id=stopBtn
    Log    ✅ Translated text was read aloud successfully!