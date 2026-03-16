import pandas as pd    # library for working with data tables
# Optional imports (commented out since not currently used)
# import torch           # PyTorch library for running neural networks
# from transformers import pipeline     # hugging faces' library for using pre-trained AI models
from openai import OpenAI
import time
import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment variables

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# BART model (neural network architecture)
print("Loading classification model...")
# pipeline() creates an AI tool to use
# Zero-shot is the task the AI should do - it classifies things it wasn't trained on
#classifier = pipeline("zero-shot-classification", 
                     #model="facebook/bart-large-mnli",                # specific AI model
                     #device=0 if torch.cuda.is_available() else -1)   # where to run model? checks for NVIDIA GPU

# Initialize OpenAI client lazily (only when needed)
client = None
client_api_key = None

def get_openai_client(api_key=None):
    """Get or create OpenAI client"""
    global client, client_api_key
    effective_key = (api_key or OPENAI_API_KEY or "").strip()
    if client is None or client_api_key != effective_key:
        if not effective_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        client = OpenAI(api_key=effective_key)
        client_api_key = effective_key
    return client

print("Model loaded!")

# 9 categories from Paul-Elder framework and their questions to test CR
critical_thinking_categories = {
    'CT1': {
        'name': "Clarity",
        'example_questions': [
            "Could you elaborate on that point?",
            "Could you express that point in another way?",
            "Could you give me an illustration?",
            "Could you give me an example?",
            "Let me state in my own words what I think you just said.",
            "Am I clear about your meaning?"
        ]
    },
    'CT2': {
        'name': "Accuracy",
        'example_questions': [
            "Is that really true?",
            "How could we check to see if that is accurate?",
            "How could we find out if that is true?"
        ]
    },
    'CT3': {
        'name': "Precision",
        'example_questions': [
            "Could you give me more details?",
            "Could you be more specific?"
        ]
    },
    'CT4': {
        'name': "Relevance",
        'example_questions': [
            "How is this idea connected to the question?",
            "How does that bear on the issue?",
            "How does this idea relate to this other idea?",
            "How does your question relate to the issue we are dealing with?"
        ]
    },
    'CT5': {
        'name': "Depth",
        'example_questions': [
            "How does your answer address the complexities in the question?",
            "How are you taking into account the problems in the question?",
            "How are you dealing with the most significant factors in the problem?"
        ]
    },
    'CT6': {
        'name': "Breadth",
        'example_questions': [
            "Do we need to consider another point of view?",
            "Is there another way to look at this question?",
            "What would this look like from a conservative standpoint?",
            "What would this look like from the point of view of…?"
        ]
    },
    'CT7': {
        'name': "Logicalness",
        'example_questions': [
            "Does all of this fit together logically?",
            "Does this really make sense?",
            "Does that follow from what you said?",
            "How does that follow from the evidence?",
            "Before, you implied this, and now you are saying that. I don't see how both can be true."
        ]
    },
    'CT8': {
        'name': "Significance",
        'example_questions': [
            "What is the most significant information we need to address this issue?",
            "How is that fact important in context?",
            "Which of these questions is the most significant?",
            "Which of these ideas or concepts is the most important?"
        ]
    },
    'CT9': {
        'name': "Fairness",
        'example_questions': [
            "Is my thinking justified given the evidence?",
            "Am I taking into account the weight of the evidence that others might advance in the situation?",
            "Are these assumptions justified?",
            "Is my purpose fair given the implications of my behavior?",
            "Is the manner in which I am addressing the problem fair or is my vested interest keeping me from considering the problem from alternative viewpoints?",
            "Am I using concepts justifiably, or am I using them unfairly in order to manipulate someone (and selfishly get what I want)?"
        ]
    },
    'Non-CT': {
        'name': "Non-Critical Thinking",
        'example_questions': [
            "Just give me the answer",
            "Tell me what to do",
            "What's the solution?",
            "Do this for me",
            "Show me the code",
            "Give me the correct answer",
            "What should I write?",
            "Just tell me"
        ]
    }
}

def classify_with_ai(text, api_key=None):
    # Classify message using AI with your 9 critical thinking categories
    # The AI learns from the example questions to understand each category
    
    # Build the prompt with your categories and examples
    categories_text = ""
    for code, cat in critical_thinking_categories.items():
        examples = " | ".join(cat['example_questions'][:3])  # Use first 3 examples
        categories_text += f"\n{code} - {cat['name']}: Examples: {examples}"
    
    # Create the prompt
    prompt = f"""You are classifying user messages into critical thinking categories based on the Paul-Elder framework.

    Categories and their example questions:
    {categories_text}

    Instructions:
    - Classify the following message into ONE of the categories above
    - Return ONLY the category code (like CT1, CT2, etc.) and the category name
    - Format your response as: "CODE: Name"

    Message to classify: "{text}"

    Classification:"""

    # Call OpenAI API
    openai_client = get_openai_client(api_key=api_key)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",  # Cheaper model, or use "gpt-4o" for best quality
        messages=[
            {"role": "system", "content": "You are a critical thinking classification assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,  # Lower = more consistent
        max_tokens=50
    )
    
    # Extract the response
    classification_text = response.choices[0].message.content.strip()
    
    # Parse the response (expecting "CT1: Clarity" format)
    if ":" in classification_text:
        parts = classification_text.split(":")
        category_code = parts[0].strip()
        category_name = parts[1].strip() if len(parts) > 1 else ""
    else:
        # Fallback if format is different
        category_code = "Unknown"
        category_name = classification_text
    
    # Calculate a confidence score (GPT doesn't give one by default)
    # You could ask for it in the prompt, or just set a default
    confidence = 0.85  # Default confidence
    
    return {
        'category': category_name,
        'category_code': category_code,
        'confidence': confidence,
    }

def analyze_chat_history(messages, progress_callback=None, unit_label="message", api_key=None):
    # analyze a list of items (messages/conversations) and return statistics
    results = []
    total = len(messages)
    label_plural = f"{unit_label}s" if not unit_label.endswith("s") else unit_label
    
    log_message = f"\nAnalyzing {total} {label_plural}...\n"
    print(log_message)
    if progress_callback:
        progress_callback(0, total, log_message.strip())
    
    for i, msg in enumerate(messages, 1):
        log_message = f"Processing {unit_label} {i}/{total}..."
        print(log_message, end='\r')
        if progress_callback:
            progress_callback(i, total, log_message)
        
        classification = classify_with_ai(msg, api_key=api_key)
        results.append({
            'message': msg,
            'category': classification['category'],
            'confidence': classification['confidence'],
        })

        # Wait 20 seconds every 3 messages to avoid rate limit
        if i % 3 == 0 and i < len(messages):
            log_message = f"\nRate limit: Waiting 20 seconds... ({i}/{total} {label_plural} done)"
            print(log_message)
            if progress_callback:
                progress_callback(i, total, log_message.strip())
            time.sleep(20)
    
    log_message = "\nAnalysis complete!"
    print(log_message)
    if progress_callback:
        progress_callback(total, total, log_message.strip())
    
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Calculate statistics
    total_messages = len(df)
    non_critical_count = len(df[df['category'] == 'Non-Critical Thinking'])
    critical_thinking_count = total_messages - non_critical_count
    
    ct_percentage = (critical_thinking_count / total_messages * 100) if total_messages > 0 else 0
    
    # Count per category
    category_counts = df['category'].value_counts()
    
    stats = {
        'total_messages': total_messages,
        'critical_thinking_count': critical_thinking_count,
        'non_critical_count': non_critical_count,
        'critical_thinking_percentage': ct_percentage,
        'category_breakdown': category_counts.to_dict()
    }
    
    return df, stats

# Test with sample messages
if __name__ == "__main__":
    
    test_messages = [
        # Clarity examples
        "Could you explain what polymorphism means in another way?",
        "Let me say this back - you're saying that recursion calls itself?",
        
        # Accuracy examples
        "Is it really true that Python is slower than C++?",
        "How could we verify if this algorithm is O(n²)?",
        
        # Precision examples
        "Could you be more specific about which index causes the error?",
        "Can you give me more details on how the sort works?",
        
        # Relevance examples
        "How does learning Big O relate to writing better code?",
        "How does this sorting algorithm connect to our original problem?",
        
        # Depth examples
        "How does your solution address the edge cases in this problem?",
        "How are you accounting for memory constraints?",
        
        # Breadth examples
        "Should we consider an iterative approach instead of recursive?",
        "What would this look like from a performance optimization standpoint?",
        
        # Logicalness examples
        "Does it make sense to use a hash map if we're sorting anyway?",
        "Before you said arrays are fixed size, now you're saying they can grow. How does that work?",
        
        # Significance examples
        "Which of these bugs is most critical to fix first?",
        "What's the most important factor for our database design?",
        
        # Fairness examples
        "Am I being biased by only considering my preferred programming language?",
        "Are my assumptions about user behavior justified by the data?",
        
        # Non-critical thinking examples
        "Just give me the answer to question 5",
        "Tell me what code to write",
        "What's the solution?"
    ]
    
    print("\n\nNow testing message classification...\n")
    
    # Analyze the messages
    results_df, stats = analyze_chat_history(test_messages)
    
    # Display results
    print("="*80)
    print("CHAT CLASSIFICATION RESULTS")
    print("="*80)
    print(f"\nTotal Messages: {stats['total_messages']}")
    print(f"Critical Thinking Messages: {stats['critical_thinking_count']} ({stats['critical_thinking_percentage']:.1f}%)")
    print(f"Non-Critical Thinking Messages: {stats['non_critical_count']} ({100-stats['critical_thinking_percentage']:.1f}%)")
    
    print("\n" + "="*80)
    print("CATEGORY BREAKDOWN")
    print("="*80)
    for category, count in stats['category_breakdown'].items():
        percentage = (count / stats['total_messages'] * 100)
        print(f"{category}: {count} ({percentage:.1f}%)")
    
    print("\n" + "="*80)
    print("DETAILED MESSAGE CLASSIFICATION")
    print("="*80)
    for idx, row in results_df.iterrows():
        ct_label = "✓ CT" if row['category'] != 'Non-Critical Thinking' else "✗ Non-CT"
        confidence = row['confidence'] * 100
        print(f"\n[{ct_label}] {row['message']}")
        print(f"    → {row['category']} ({confidence:.1f}% confident)")
    
    # Save to CSV
    results_df.to_csv('classified_messages.csv', index=False)
    print("\n" + "="*80)
    print("Results saved to 'classified_messages.csv'")