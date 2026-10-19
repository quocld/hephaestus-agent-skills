# GitLab without glab

Used by `worktree-flow` section 4 step 4 when the remote is GitLab and `glab` is not installed or not authenticated.

- Suggest `! glab auth login` once `glab` is installed.
- Until then, the existing-MR checks in `worktree-flow` sections 1 and 6 rely on `git branch -r` and the user; say so in your report.
- Never read a stored git password or credential to call the GitLab API instead.

## Create the MR

Push options create the MR, but only on a push that carries commits; nothing is sent when nothing is pushed:

```bash
git push -u origin HEAD -o merge_request.create -o merge_request.target=<int> -o merge_request.title="<title>"
```

- A draft MR adds `-o merge_request.draft`.
- Push options cannot hold newlines, so `merge_request.description` takes one line only.

## The full body

For the full body, open a prefilled form for the user, every value URL-encoded:

```text
https://<host>/<group path>/<repo>/-/merge_requests/new?merge_request[source_branch]=<branch>&merge_request[target_branch]=<int>&merge_request[title]=<title>&merge_request[description]=<body>
```

- Past about 8 KB of URL, prefill a short body and have the user paste the rest after creating the MR.
- The MR does not exist until the user submits the form; report it that way.

## Later body updates

Updating the body of an existing MR (for example the `verify-loop` table) becomes a step for the user: hand them the new text to paste.
