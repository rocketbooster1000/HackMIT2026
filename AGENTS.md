# EdTech Knowledge Map — Hackathon Project

## Project Overview

This is a hackathon edtech project that turns a student's syllabus into an interactive knowledge map.

The core idea is:

> Upload a syllabus → extract topics → create a prerequisite graph → upload learning materials → associate them with topics → organize topics with tags → filter the graph.

The application should feel like a clean, modern workspace inspired by the Claude interface.

This is a hackathon project. Prioritize a polished, working demo over production scalability, complex architecture, or unnecessary features.

---

# Core User Experience

The primary user flow is:

1. Open the application.
2. Click `+` to create a new sandbox.
3. A new sandbox/workspace opens.
4. Click the `+` inside the sandbox.
5. Upload a syllabus OR manually create a node.
6. The syllabus is analyzed and topics are extracted.
7. Prerequisite relationships are generated.
8. The knowledge map appears.
9. Click a node to inspect it.
10. Upload lecture notes/slides and associate them with topics.
11. Select multiple nodes.
12. Apply a tag such as `Exam 1`.
13. Filter the graph by tags.

The core product is the knowledge map.

Do not allow secondary features to distract from this workflow.

---

# UI Design

The application should be visually inspired by Claude's interface.

Do NOT copy Claude's branding or exact UI.

Use the reference screenshot provided by the developer as inspiration for:

- Dark theme
- Left sidebar
- Minimal interface
- Spacious layout
- Rounded controls
- Subtle borders
- Clean typography
- Bottom profile area
- Main workspace
- Simple contextual controls

The interface should feel like a workspace rather than a traditional dashboard.

---

# Overall Layout

Use a persistent left sidebar and a main workspace.

Conceptually:

```text
┌──────────────────┬──────────────────────────────────────────┐
│                  │                                          │
│  + New Sandbox   │                                          │
│                  │                                          │
│  Sandboxes       │             Current Sandbox              │
│                  │                                          │
│  ○ Calculus      │                                          │
│  ○ Physics       │             Knowledge Map                │
│  ○ Biology       │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
│  ─────────────   │                                          │
│  👤 Daniel       │                                          │
│  Student         │                                          │
└──────────────────┴──────────────────────────────────────────┘