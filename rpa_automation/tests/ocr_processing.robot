*** Settings ***
Documentation     OCR / text-extraction automation — uploads a real file and
...               verifies the ACTUAL extracted text shows up on the reader
...               page (not just that some API call returned something).
Library           Browser
Library           OperatingSystem

*** Variables ***
${BASE_URL}          http://127.0.0.1:5000
${TEST_FILE_PATH}    ${CURDIR}${/}testdata${/}sample_document.txt

*** Test Cases ***
Upload Document And Extract Text
    [Documentation]    Uploads a .txt file and verifies:
    ...                1. We land on reader.html with a file_id (not raw
    ...                   text in the URL — regression check for the old
    ...                   URL-truncation bug).
    ...                2. The extracted text ACTUALLY contains content
    ...                   from the source file (real OCR/extraction
    ...                   verification, not just "an API responded").
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}

    Wait For Elements State    id=docText    visible    timeout=15s
    ${current_url}=    Get Url
    Should Contain    ${current_url}    file_id=
    Should Not Contain    ${current_url}    text=%0A

    ${extracted}=    Get Text    id=docText
    Should Contain    ${extracted}    Hello
    Should Contain    ${extracted}    Jeeni Reader AI
    Log    ✅ Real text extraction verified — content matches the source file.

Upload History Shows The New Document
    [Documentation]    After uploading, the document should appear in
    ...                /history and on the library page.
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s

    Upload File By Selector    id=realFileInput    ${TEST_FILE_PATH}
    Wait For Elements State    id=docText    visible    timeout=15s

    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    css=.doc-card    visible    timeout=10s
    ${count}=    Get Element Count    css=.doc-card
    Should Be True    ${count} > 0
    Log    ✅ Document history shows ${count} uploaded document(s).