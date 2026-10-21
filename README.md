# exchange-test-mod

A mod for Pokémon Emerald Expansion on ADMG-101, published through ADMG Exchange.

> Created from the ADMG Exchange mod template. Replace this README with your mod's own description; keep the
> "Publishing" section if it helps you.

## What's here

| Path | What it is |
|---|---|
| `mod/` | The mod itself: `mod.json` and its data. Everything in `mod/` is packaged. |
| `.admg/exchange.json` | How ADMG Exchange describes your project (id, title, licence, the release asset). |
| `LICENSE` | Your open-source licence. Exchange requires one (see below). |
| `.github/workflows/release.yml` | Builds, attests and publishes a release for every version tag. |
| `.github/workflows/check.yml` | Checks the project on every push and pull request. |
| `.github/workflows/setup.yml` | Ran once when the repository was created, filling in your project id and names. |
| `.admg/package.py` | The packaging tool the workflows use; you can run it locally too. |

## Publishing

1. **Edit** `mod/` (your files and `mod.json`) and `.admg/exchange.json` (title, summary, categories, tags).
2. **Install the ADMG Exchange GitHub App** on this repository: open the App's page, choose **Install**, pick
   **Only select repositories** and select this one. The App can only read; it never changes your repository.
   You can also start from the ADMG-101 launcher: **Exchange → Creator Hub → Submit Project**.
3. **Release**: set the same version in `mod/mod.json`, commit, then tag that commit and push the tag:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

   The release workflow builds `<your-mod>-1.0.0.zip`, records its build provenance and publishes the GitHub release.
4. **Track** your submission in the launcher's Creator Hub, or on your release's Actions run. Exchange registers new
   repositories and discovers releases about every 30 minutes, checks them, and queues them for review. After a
   moderator approves a release it appears in ADMG Exchange.

Updates work the same way: change the version, commit, tag, push. Each release is reviewed on its own; players are
offered approved updates only.

## Requirements

- **A public repository.** Exchange lists public source only.
- **An open-source licence.** `project.license.name` in `.admg/exchange.json` is its SPDX identifier (for example
  `MIT`, `Apache-2.0`, `GPL-3.0-or-later`, `MPL-2.0`, `CC-BY-4.0`), and `LICENSE` holds its unmodified text, so GitHub
  recognises it. This template starts with MIT; choose the licence you want before your first release.
- **Your own work.** No game ROMs, ROM patches or extracted game assets. Packages are checked for them.
- **Releases from the workflow.** Exchange accepts only packages built by this repository's workflow from the tagged
  commit, with their build provenance.

## Mods with code

Put the C# project under `src/`. The release workflow then builds it against the ADMG SDK reference kit with a
deterministic configuration and copies `<mod id>.dll` into `mod/` before packaging. Set the repository variables
`ADMG_SDK_KIT_URL` and `ADMG_SDK_KIT_SHA256` to the kit release you build against. The .NET SDK adds SourceLink for
GitHub repositories automatically; keep these settings in your project so the DLL points back to the exact commit and
builds the same way every time:

```xml
<PropertyGroup>
  <Deterministic>true</Deterministic>
  <PublishRepositoryUrl>true</PublishRepositoryUrl>
  <EmbedUntrackedSources>true</EmbedUntrackedSources>
  <DebugType>embedded</DebugType>
</PropertyGroup>
```

## Check locally

```bash
python3 .admg/package.py check
python3 .admg/package.py build --version 1.0.0 --out dist
```

## Help

See the publisher guide in the ADMG Exchange index repository: publishing, the GitHub App, troubleshooting, updates
and appeals.
