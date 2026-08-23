Anti-Bagu Agent for macOS

START

1. Open Terminal.
2. Change to this extracted folder.
3. Run: ./anti-bagu-agent
4. The agent opens your browser for sign-in when needed.
5. Keep the terminal window open while using Anti-Bagu.

The login session is stored in ~/.anti-bagu/session.json with owner-only
permissions. Model service keys are managed on the website under Settings and
are never requested by the CLI.

SCREENSHOT

While an interview is running, press Option+Space to capture the display under
the pointer. The screenshot is analyzed as an exclusive task, so spoken
questions cannot interrupt it. A second screenshot is ignored until the first
analysis finishes.

PERMISSIONS

The first launch requests two separate macOS permissions:

- Screen & System Audio Recording, used for interview audio.
- Microphone, used for your voice.

After changing a permission, quit the agent completely and run it again.

If interview audio is unavailable, open:

System Settings > Privacy & Security > Screen & System Audio Recording

Enable Terminal or anti-bagu-agent, depending on which item macOS displays.

GATEKEEPER

If macOS says Apple cannot verify anti-bagu-agent:

1. Open System Settings > Privacy & Security.
2. Find the blocked anti-bagu-agent message.
3. Click Open Anyway.
4. Run ./anti-bagu-agent again.

COMMANDS

./anti-bagu-agent          Start the agent
./anti-bagu-agent status   Show account, audio, and permission status
./anti-bagu-agent login    Sign in with a different account

Set NO_COLOR=1 to disable colored output.
