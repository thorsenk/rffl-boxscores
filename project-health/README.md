# Multi-AI Project Health Assessment System

This system enables multiple AI models to collaboratively assess project health, providing diverse perspectives and consensus-driven action plans.

## 📁 Folder Structure

```
project-health/
├── reports/           # Individual AI assessments
├── consensus/         # Multi-AI consensus plans
├── templates/         # Standardized assessment templates
└── README.md         # This file
```

## 🔄 Assessment Workflow

### 1. Individual Assessment
Each AI model performs an independent health assessment using the standardized template:

```bash
# Human request to any AI
"Please perform a project health assessment using the template in project-health/templates/health-assessment-template.md"
```

**Output**: `reports/YYYY-MM-DD_[model-name]_health-assessment.md`

### 2. Consensus Generation
After collecting 2+ individual assessments, request consensus generation:

```bash
# Human request to any AI
"Review all reports in project-health/reports/ and generate a consensus plan using the template in project-health/templates/consensus-template.md"
```

**Output**: `consensus/YYYY-MM-DD_multi-ai-consensus-plan.md`

## 📋 Assessment Categories

Each assessment evaluates:

- **Code Quality** (1-10): Linting, formatting, best practices
- **Architecture** (1-10): Structure, modularity, separation of concerns  
- **Documentation** (1-10): README, API docs, inline comments
- **Testing** (1-10): Coverage, quality, CI integration
- **CI/CD** (1-10): Pipeline health, automation, deployment
- **Dependencies** (1-10): Management, security, compatibility
- **Data Quality** (1-10): Integrity, validation, consistency
- **Maintainability** (1-10): Technical debt, refactoring needs

## 🎯 Scoring System

- **9-10**: Excellent - Industry best practices
- **7-8**: Good - Minor improvements needed
- **5-6**: Fair - Notable issues requiring attention
- **3-4**: Poor - Significant problems blocking progress
- **1-2**: Critical - Project health at risk

## 📝 Report Naming Convention

### Individual Reports
`YYYY-MM-DD_[model-name]_health-assessment.md`

Examples:
- `2025-09-07_claude-sonnet-4_health-assessment.md`
- `2025-09-07_gpt4o_health-assessment.md`
- `2025-09-07_gemini-pro_health-assessment.md`

### Consensus Plans
`YYYY-MM-DD_multi-ai-consensus-plan.md`

Example:
- `2025-09-07_multi-ai-consensus-plan.md`

## 🔍 Quality Assurance

### For Individual Assessments
- Use standardized template
- Provide specific examples and line numbers
- Include unique insights beyond template
- Score consistently across categories

### For Consensus Generation
- Reference all input reports
- Identify areas of agreement/disagreement
- Highlight conflicting recommendations
- Provide unified action plan with priorities

## 📊 Historical Tracking

### Benefits
- Track project health evolution over time
- Compare different AI perspectives on same codebase
- Measure improvement against past assessments
- Identify recurring issues across assessments

### Usage
- Run assessments monthly or after major changes
- Compare scores across time periods
- Use trends to guide long-term planning

## 🚀 Getting Started

1. **First Assessment**: Use `health-assessment-template.md` to generate initial report
2. **Multiple Perspectives**: Have 2-3 different AI models assess independently  
3. **Generate Consensus**: Create unified plan using `consensus-template.md`
4. **Take Action**: Implement prioritized recommendations
5. **Track Progress**: Re-assess after implementing changes

## 🛠️ Integration

This system can integrate with:
- GitHub Issues (link assessments to action items)
- CI/CD pipelines (automated health checks)
- Project management tools (roadmap planning)
- Documentation systems (embed health metrics)

---

**Next Steps**: Use the templates in `templates/` to begin your first multi-AI assessment cycle.