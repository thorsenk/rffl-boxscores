# Knowledge Library Prompts

This directory contains reusable prompts for creating knowledge entries from AI conversations.

## Available Prompts

### 1. `save-full-conversation.md`
- **Purpose:** Save entire conversation thread (user questions + AI responses)
- **Use when:** You want comprehensive context and learning journey
- **Best for:** Complex topics, multi-step problem solving, learning sessions

### 2. `save-ai-response-only.md`
- **Purpose:** Save only AI responses as standalone knowledge
- **Use when:** You want specific explanations without conversational context
- **Best for:** Tutorials, solutions, reference materials, specific explanations

## How to Use

1. Copy the appropriate prompt from the files above
2. Fill in the bracketed placeholders (Topic, Learning Level, Tags)
3. Send the prompt to your AI assistant
4. The AI will create a properly formatted knowledge entry

## File Naming Convention

Knowledge entries are automatically saved with the format:
`knowledge_YYYY-MM-DD_HHMMSS_[topic].md`

## Template Location

All prompts reference the `knowledge_entry_template.md` located in:
`~/Knowledge-Library/templates/knowledge_entry_template.md`

## Output Location

Knowledge entries are saved to:
`~/Knowledge-Library/knowledge-entries/`
