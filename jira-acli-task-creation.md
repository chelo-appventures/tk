# Jira to tk: Task Creation Guide

This document provides a standardized workflow for AI agents to fetch Jira tasks using the Atlassian CLI (`acli`) and convert them into local Markdown files compatible with the `tk` task manager.

## 1. Prerequisites

- **acli** installed and authenticated.
- **tk** initialized (`tk init`) with a task directory structure (default: `~/tasks`).
- A target project directory already created in `tk` (e.g., via `tk proj {name}`).

## 2. Authentication Check

Before fetching, verify the session is active:
```bash
acli jira project list --limit 1
```
If it fails, the agent should prompt the user to run `acli auth login`.

## 3. Fetching Tasks via JQL

To fetch assigned, incomplete tasks for a specific project in JSON format:

```bash
acli jira workitem search \
  --jql "project = {PROJECT_KEY} AND assignee = currentUser() AND status != Done" \
  --fields "key,summary,status,priority,description" \
  --json
```

### JQL Parameters:
- `{PROJECT_KEY}`: The uppercase Jira project identifier (e.g., PROJ).
- `currentUser()`: Ensures only tasks assigned to the authenticated user are fetched.
- `status != Done`: Filters out completed work.

## 4. Conversion to tk Format

For each task in the JSON output, the agent should generate a file in the project's `backlog` directory.

### Naming Convention:
`YYYYMMDD-{JIRA_KEY}-{slug}.md`
- `YYYYMMDD`: Current date.
- `{JIRA_KEY}`: e.g., PROJ-123.
- `{slug}`: Lowercase summary with spaces replaced by hyphens.

### File Content Template:
The agent should use the local `~/.tasks/.templates/task.md` or follow this structure:

```markdown
# Task: {summary}

- **Status:** #backlog
- **Created:** {YYYY-MM-DD}
- **Project:** {PROJECT_KEY}

## 📝 Description
{description}

## ✅ TODO
- [ ] {summary}

## 📓 Notes
- **Jira Key:** {key}
- **Priority:** {priority}

## 📎 References
- https://{your-site}.atlassian.net/browse/{key}
```

## 5. Agent Instructions for Automation

When an agent is tasked with "syncing Jira tasks," it should:
1. Identify the Jira `{PROJECT_KEY}` and the local `tk` project name.
2. Execute the `acli` search command.
3. Parse the JSON.
4. Check if a file with the same `{JIRA_KEY}` already exists in any subfolder of the local project to avoid duplicates.
5. Create new files for missing tasks in the `backlog/` directory.
6. Report a summary of how many tasks were imported.
