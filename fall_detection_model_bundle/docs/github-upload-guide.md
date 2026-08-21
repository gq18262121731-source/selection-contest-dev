# GitHub Upload Guide

This document describes the recommended way to upload this model bundle to GitHub for team use.

## Recommended Long-Term Method: SSH

SSH is the best long-term option for a team because it avoids browser login prompts, CAPTCHA issues, and repeated token input.

### 1. Generate SSH Key

```powershell
ssh-keygen -t ed25519 -C "your_email@example.com"
```

Default output:

```text
C:\Users\你的用户名\.ssh\id_ed25519
C:\Users\你的用户名\.ssh\id_ed25519.pub
```

### 2. Start SSH Agent

```powershell
Get-Service -Name ssh-agent | Set-Service -StartupType Manual
Start-Service ssh-agent
```

### 3. Add Key

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### 4. Add Public Key to GitHub

Copy:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Then add it in GitHub:

```text
Settings → SSH and GPG keys → New SSH key
```

### 5. Clone Repository

```powershell
git clone git@github.com:gq18262121731-source/410health.git D:\Program\410health_git
```

### 6. Create Branch

```powershell
git -C D:\Program\410health_git checkout -b feature/fall-detection-model-bundle
```

### 7. Copy Model Bundle

Copy the model delivery folder into:

```text
D:\Program\410health_git\fall_detection_model_bundle
```

### 8. Commit and Push

```powershell
git -C D:\Program\410health_git add fall_detection_model_bundle
git -C D:\Program\410health_git commit -m "Add fall detection model bundle and documentation"
git -C D:\Program\410health_git push -u origin feature/fall-detection-model-bundle
```

## Emergency HTTPS Method: PAT + GIT_ASKPASS

GitHub no longer recommends account passwords for HTTPS Git authentication. Use a Personal Access Token instead.

Required PAT permission:

```text
Contents: Read and write
```

If you need to create PRs through API, add:

```text
Pull requests: Read and write
```

### HTTPS Upload Example

```powershell
git clone https://github.com/gq18262121731-source/410health.git D:\Program\410health_git
git -C D:\Program\410health_git checkout -b feature/fall-detection-model-bundle
git -C D:\Program\410health_git config user.name "your-github-username"
git -C D:\Program\410health_git config user.email "your-email@example.com"
git -C D:\Program\410health_git add fall_detection_model_bundle
git -C D:\Program\410health_git commit -m "Add fall detection model bundle and documentation"
```

Create temporary askpass script:

```powershell
$askpass = "D:\Program\410health_git\.git\temp_askpass.cmd"

@'
@echo off
set prompt=%~1
echo %prompt% | findstr /I "Username" >nul
if %errorlevel%==0 (
  echo YOUR_USERNAME
  exit /b 0
)
echo YOUR_PAT
'@ | Set-Content -LiteralPath $askpass -Encoding ASCII

$env:GIT_ASKPASS = $askpass
$env:GIT_TERMINAL_PROMPT = "0"

git -C D:\Program\410health_git push -u origin feature/fall-detection-model-bundle

Remove-Item $askpass -Force
Remove-Item Env:\GIT_ASKPASS -ErrorAction SilentlyContinue
Remove-Item Env:\GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
```

Never commit PATs, API keys, or temporary credential scripts.

## Common Problems

### fatal: not a git repository

You are in a normal folder, not a Git working tree. Clone the repository first.

### detected dubious ownership

If the repository was cloned by another Windows user, Git may block access. Use:

```powershell
git config --global --add safe.directory D:/Program/410health_git
```

### Permission denied

Common causes:

- No repository write permission.
- PAT permission too small.
- SSH key not added to GitHub.

### Large File Rejected

GitHub blocks files over 100 MB. Use Git LFS or do not upload large weights directly.

The current model weights are small enough to upload directly.

## Download for Other Team Members

After upload, team members can clone:

```powershell
git clone https://github.com/gq18262121731-source/410health.git
```

or with SSH:

```powershell
git clone git@github.com:gq18262121731-source/410health.git
```
