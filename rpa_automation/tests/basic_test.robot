*** Settings ***
Documentation     Basic smoke test — verifies the backend is up and the
...               core pages actually load, with real assertions instead
...               of just Log statements.
Library           Browser
Library           RequestsLibrary

*** Variables ***
${BASE_URL}    http://127.0.0.1:5000

*** Test Cases ***
Backend History Endpoint Is Reachable
    [Documentation]    /history is a real, existing endpoint — used here
    ...                as a lightweight "is the server alive" check.
    ...                (The old /tts endpoint doesn't exist in app.py,
    ...                which is why it always looked like it passed —
    ...                GET doesn't fail on a 404 unless you check it.)
    ${response}=    GET    ${BASE_URL}/history    expected_status=200
    Should Be Equal As Strings    ${response.status_code}    200
    Log    ✅ Backend is up — /history returned 200.

Home Page Loads
    New Page    ${BASE_URL}/
    Get Title    ==    Jeeni.Reader AI
    Get Text    css=.logo    ==    Jeeni.Reader AI
    Log    ✅ Home page loaded with correct title.

Upload Page Loads
    New Page    ${BASE_URL}/upload.html
    Wait For Elements State    id=uploadBtn    visible    timeout=10s
    Get Text    id=uploadBtn    ==    Choose a document
    Log    ✅ Upload page loaded and upload button is visible.

Auth Page Loads
    New Page    ${BASE_URL}/auth.html
    Wait For Elements State    id=loginForm    visible    timeout=10s
    Log    ✅ Auth page loaded with login form visible.