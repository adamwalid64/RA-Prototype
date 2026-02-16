# Backend Setup Instructions

## Required Environment Variables

The classification feature requires an OpenAI API key to analyze prompts using the Paul-Elder framework.

### Setting up OpenAI API Key

1. **Get your API key:**
   - Go to https://platform.openai.com/api-keys
   - Sign in or create an account
   - Create a new API key

2. **Create a `.env` file:**
   - In the `backend` directory, create a file named `.env`
   - Add the following line:
     ```
     OPENAI_API_KEY=your_actual_api_key_here
     ```
   - Replace `your_actual_api_key_here` with your actual OpenAI API key

3. **Example `.env` file:**
   ```
   OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

4. **Optional – ChatGPT export for group analysis**  
   To analyze prompts by group (e.g. by assignment) when running `Models/grade_prompts.py`:
   - Set `CHAT_EXPORT_JSON_PATH` in `.env` to the path of your ChatGPT export JSON, or  
   - Place your export file at `backend/chat_export.json`  
   If the file exists, the script loads it, groups conversations by topic, and grades each group.

5. **Restart the Flask server** after creating/updating the `.env` file

### Important Notes

- Never commit your `.env` file to version control
- Keep your API key secure and private
- The `.env` file is already in `.gitignore` to prevent accidental commits

### Testing the Setup

Once you've set up your `.env` file:
1. Start the Flask server: `python app.py`
2. Upload a ChatGPT export file through the frontend
3. Click "Analyze 50 Sample Prompts" button
4. The classification should work without errors

### Running prompt grading by group (script)

From the `backend` directory:
```bash
python Models/grade_prompts.py
```
- If `CHAT_EXPORT_JSON_PATH` is set (or `backend/chat_export.json` exists), the script loads your ChatGPT export, groups prompts by topic, and grades each group. Results are written to `Models/Exports/group_grading_results.csv`.
- Otherwise, it runs on sample prompts and writes to `Models/Exports/grading_results.csv`.
