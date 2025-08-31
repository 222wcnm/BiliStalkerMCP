## Brief overview
This rule file specifies the terminal environment preferences for this system. The user is using PowerShell on Windows, so all terminal commands should be compatible with PowerShell syntax rather than bash or other shell environments.

## Terminal environment
- The default shell is PowerShell on Windows 11
- Use PowerShell-compatible commands and syntax
- Avoid bash-specific syntax like `&&` for command chaining
- Use PowerShell equivalents like `;` or `&&` alternatives
- Path separators should use backslashes (`\`) or forward slashes (`/`) as appropriate

## Command compatibility
- Use `Get-Content` instead of `cat`
- Use `Select-Object` instead of `head`/`tail`
- Use `findstr` or `Select-String` instead of `grep`
- Use `where` instead of `which`
- Use PowerShell cmdlets when available

## Script execution
- PowerShell scripts should use `.ps1` extension
- Batch files should use `.bat` or `.cmd` extension
- Avoid Unix shell scripts (`.sh`) unless specifically needed

## Path handling
- Use cross-platform path handling when possible
- Windows paths use backslashes, but forward slashes are often acceptable
- Use PowerShell's `Join-Path` for complex path operations

## Global applicability
This rule applies to all projects and tasks on this system, as it's a system-level preference rather than project-specific.
