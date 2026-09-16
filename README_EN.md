# Jewel Level Scatter Tuning

English | [简体中文](README.md)

## Choose a version

This branch contains the experimental candidate optimizer. It is disabled by default and is kept separate from the stable version.

| Version | Source | Download |
|---|---|---|
| Stable | [main](https://github.com/sn246akeak/jewel-level-scatter-tuning/tree/main) | [Stable ZIP](https://github.com/sn246akeak/jewel-level-scatter-tuning/archive/refs/heads/main.zip) |
| Draft PR experiment | [Experimental branch](https://github.com/sn246akeak/jewel-level-scatter-tuning/tree/codex/profile-candidate-optimizer) | [Experimental ZIP](https://github.com/sn246akeak/jewel-level-scatter-tuning/archive/refs/heads/codex/profile-candidate-optimizer.zip) |

Use the repository's branch selector to switch versions. See [the PR description (Chinese)](PR_DESCRIPTION.md) for the motivation, implementation, results, and limitations.

A Codex Skill for pixel-art jewel sorting levels. It analyzes completed artwork, designs playable pre-fill boards, and combines rule-based validation with AI visual review to preserve playability, visual structure, and production consistency.

## Background

I created this Skill while working as a **Level Designer at Beijing Zhixingyuan Technology Co., Ltd.** I identified that random scatter could damage visual structure, while manual tuning was time-consuming and produced inconsistent review results. By collaborating with AI, I turned level classification, rule prioritization, scripted validation, and visual review into a reusable workflow that improves both production speed and accuracy.

## Capabilities

- Analyze completed pixel art and select an appropriate level-design strategy
- Design legal, readable, and visually clustered pre-fill boards
- Run deterministic checks for colors, connectivity, and scatter quality
- Combine AI visual review with final editor-state verification
- Preserve analysis, profiles, boards, and reports for restoration and retrospectives

## Usage

Install this directory in your Codex skills folder, then invoke:

```text
$jewel-level-scatter-tuning
```

See [SKILL.md](SKILL.md) for the complete workflow and constraints. Some features require access to the company's internal KStage editor.

## Structure

```text
SKILL.md      Skill entry point and execution workflow
references/   Classification, rules, design, validation, and editor workflow
scripts/      Board-processing and deterministic validation scripts
agents/       Codex display and invocation metadata
```
