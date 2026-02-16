import pandas as pd
from openai import OpenAI
import time
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = None

def get_openai_client():
    """Get or create OpenAI client (uses OPENAI_API_KEY from .env)."""
    global client
    if client is None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        client = OpenAI(api_key=OPENAI_API_KEY)
    return client

# Call the ChatGPT 4o mini model 
def classify_with_openai(prompt, json_mode=False):

    messages = [
        {"role": "system", "content": "You are an expert in self-regulated learning, educational psychology, and cognitive psychology."},
        {"role": "user", "content": prompt}
    ]
    
    # for error handling
    try:
        api = get_openai_client()
        # if we are expecting a response in the form of JSON or dictionary (for COPES & BLOOMS)
        if json_mode:
            response = api.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=200,   # json needs extra formatting characters ({}[]"")
                response_format={"type": "json_object"}  # JSON only return format
            )
        else:
            # if we are expecting plain text as a response (SRL Zimmerman)
            response = api.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=100
            )
        
        # get the first result that gpt returns to us and gets actual text from response object
        result = response.choices[0].message.content.strip()
        
        # if the response is json, create a dictionary using what's returned
        if json_mode:
            return json.loads(result)
        else:
            return result        # plain string
    
    # if anything goes wrong (network issues, API rate exceeded, malformed json, etc)      
    except Exception as e:
        print(f"API Error: {e}")
        return None

# ============================================================================
# SRL FRAMEWORK CODE CLASSIFICATION
# ============================================================================
def classify_zimmerman_phase(message, conversation_context=None):
    context_str = ""
    # if the there are previous messages, use them to get a better classification sense
    if conversation_context:
        context_str = "\nRecent context: " + " | ".join(conversation_context)
    
    prompt = f"""Classify this message into ONE Zimmerman SRL phase.

    FORETHOUGHT: Task analysis - goal setting/strategic planning. 
                 Self-motivation beliefs - self-efficacy, outcome expectations, intrinsic interest/value, goal orientation
    - Indicators: "I want to learn", "My goal is", "I should start by", future tense planning

    PERFORMANCE: self control - self-instruction, imagery, attention focusing, task strategies. 
                 Self-observation - self-recording, self-experimentation
    - Indicators: "I'm implementing", "I'm trying", asking clarifying questions during work

    SELF_REFLECTION: Self-judgment - self-evaluation, casual attribution. 
                     Self-reaction - self-satisfaction/affect, adaptive defensive
    - Indicators: "That didn't work", "I understand now", "I should have", past tense reflection

    Message: "{message}"{context_str}

    You MUST categorize the message into one of the phases and return ONLY one word: forethought, performance, or self_reflection"""
    
    return classify_with_openai(prompt, json_mode=False)
    

def analyze_copes_components(message, zimmerman_phase):
    prompt = f"""Analyze this message for COPES components from Winne and Hadwin's model of SRL within the {zimmerman_phase} phase of Zimmermans SRL model.

    Return JSON with each component as 0 (absent) or 1 (present):

    C - CONDITIONS: Resources available or constraints mentioned?
    O - OPERATIONS: Cognitive processes (or tactics/strategies) shown?
    P - PRODUCTS: Information created by operations (new knowledge)?
    E - EVALUATIONS: Self-monitoring or assessment? Feedback; either internal from student or external from teacher/peer
    S - STANDARDS: Success criteria referenced? Criteria against which products are evaluated

    Message: "{message}"

    You MUST return the answer in JSON format: {{"C": ~, "O": ~, "P": ~, "E": ~, "S": ~, "total": ~}}
    Replace the '~' with whether or not that component is present in the message and put the total amount of COPES components present in the total"""
    
    # needs a result in the form of JSON
    result = classify_with_openai(prompt, json_mode=True)
    
    return result


def classify_blooms_level(message):
    prompt = f"""Classify using Bloom's Taxonomy (1956). Return JSON.

    Levels:
    1. KNOWLEDGE: Knowledge as defined here includes those behaviors and test situations which emphasize the remembering, either by recognition or recall, of ideas, material, or phenomena - Example behaviors being: define, list, name, state, recall
    2. COMPREHENSION: Include those objectives, behaviors, or responses which represent an understanding of the literal message contained in a communication  
    3. APPLICATION: Given a problem new to the student, he will apply the appropriate abstraction without having to be prompted as to which abstraction is correct wo without having to be shown how to use it in that situation
    4. ANALYSIS: Analysis emphasizes the breakdown of the material into its constituent parts and detection of the relationships of the parts and of the way they are organized
    5. SYNTHESIS: In synthesis, on the other hand, the student must draw upon elements from many sources and put these together into a structure or pattern not clearly there before. It is to be expected that a problem which is classified as a task primarily involving synthesis will also require all of the previous categories to some extent
    6. EVALUATION: Evaluation is defined as the making of judgments about the value, for some purpose, of ideas, works, solutions, methods, material, etc. It involves the use of criteria as well as standards for appraising the extent to which particulars are accurate, effective, economical, or satisfying

    Message: "{message}"

    You MUST return the answer in JSON format: {{"level": 1-6, "level_name": ~, "confidence": ~, "rationale": ~}}
    Replace the ~ in the format with a level name, a confidence rating, and a rationale as to why you think it's that category"""
    
    # needs a result in the form of JSON
    result = classify_with_openai(prompt, json_mode=True)

    return result


# ============================================================================
# FUNCTION TO LOAD USER'S CHAT HISTORY FROM JSON
# ============================================================================
def load_chat_history_flexible(filepath):   
    # 'encoding' is used to handle special characters
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    processed_chats = []
    
    # The following is to handle chats that come in a variety of different forms in JSON
    # Handle if data is a list of chats: data = [{"chat": 1}, {"chat": 2}]
    if isinstance(data, list):
        chats = data
    # Handle if data is wrapped in an object : data = {"chats": [{"chat": 1}, {"chat": 2}]}
    elif isinstance(data, dict) and 'chats' in data:
        chats = data['chats']
    elif isinstance(data, dict) and 'conversations' in data:
        chats = data['conversations']
    else:
        raise ValueError("Unknown JSON format. Expected list of chats or object with 'chats' key")
    
    # get correct identification for categories to extract from the chat history json
    for chat in chats:
        # Try different possible field names for chat ID
        chat_id = (chat.get('uuid') or 
                   chat.get('id') or 
                   chat.get('chat_id') or 
                   chat.get('conversation_id') or 
                   'unknown')
        
        # Try different possible field names for topic/title of chat
        topic = (chat.get('name') or 
                 chat.get('title') or 
                 chat.get('topic') or 
                 chat.get('subject') or 
                 'Untitled Chat')
        
        # Try different possible field names for messages within the chat
        messages_raw = (chat.get('chat_messages') or 
                        chat.get('messages') or 
                        chat.get('conversation') or 
                        [])
        
        # Extract user messages - handle different message formats
        user_messages = []
        for msg in messages_raw:
            # Check if this is a user/human message
            sender = (msg.get('sender') or 
                     msg.get('role') or 
                     msg.get('author') or 
                     '').lower()
            
            if sender in ['human', 'user', 'person']:
                # Get message text
                text = (msg.get('text') or 
                       msg.get('content') or 
                       msg.get('message') or 
                       '')
                if text:
                    user_messages.append(text)
        
        # Skip empty chats
        if not user_messages:
            continue
        
        processed_chat = {
            'chat_id': chat_id,
            'topic': topic,
            'updated_at': chat.get('updated_at') or chat.get('timestamp') or chat.get('created_at'),
            'num_messages': len(user_messages),
            'messages': user_messages
        }
        
        processed_chats.append(processed_chat)
    
    return processed_chats

# critical thinking analysis based on sample chat prompts list
def critical_thinking_analysis(messages, progress_callback=None):
    print("\n" + "="*80)
    print("ENHANCED SRL + CRITICAL THINKING ANALYSIS: from sample chats list")
    print("="*80)
    
    srl_results = []
    total = len(messages)
    
    for i, msg in enumerate(messages):
        if progress_callback:
            progress_callback(i + 1, total, f"Analyzing message {i+1}/{total}...")
        print(f"\nAnalyzing message {i+1}/{len(messages)}...")
        
        # Get context from previous chats
        context = messages[:i] if i > 0 else []
        
        # Classify with all frameworks
        zimmerman_phase = classify_zimmerman_phase(msg, context)
        copes_analysis = analyze_copes_components(msg, zimmerman_phase)
        blooms_result = classify_blooms_level(msg)
        
        # Store results (coerce confidence to float; API may return string)
        conf_raw = blooms_result.get('confidence')
        try:
            blooms_conf = float(conf_raw) if conf_raw is not None else 0.0
        except (TypeError, ValueError):
            blooms_conf = 0.0
        srl_results.append({
            'message': msg,
            'zimmerman_phase': zimmerman_phase,
            'copes_score': copes_analysis['total'],
            'copes_components': copes_analysis,
            'blooms_level': blooms_result['level'],
            'blooms_name': blooms_result['level_name'],
            'blooms_confidence': blooms_conf
        })
        
        # Rate limiting
        if (i + 1) % 3 == 0 and i < len(messages) - 1:
            wait_msg = f"Rate limit: Waiting 20 seconds... ({i+1}/{len(messages)} done)"
            print(wait_msg)
            if progress_callback:
                progress_callback(i + 1, total, wait_msg)
            time.sleep(20)
    
    if progress_callback:
        progress_callback(total, total, "SRL analysis complete.")
    
    # Convert to DataFrame
    df = pd.DataFrame(srl_results)
    
    # Calculate statistics
    print("\n" + "="*80)
    print("ZIMMERMAN PHASE DISTRIBUTION")
    print("="*80)
    phase_counts = df['zimmerman_phase'].value_counts()
    for phase, count in phase_counts.items():
        print(f"{phase.upper()}: {count} ({count/len(df)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("COPES QUALITY SCORES")
    print("="*80)
    print(f"Average COPES Score: {df['copes_score'].mean():.2f}/5")
    print(f"High Quality (4-5): {len(df[df['copes_score'] >= 4])} messages")
    print(f"Low Quality (1-2): {len(df[df['copes_score'] <= 2])} messages")
    
    print("\n" + "="*80)
    print("BLOOM'S TAXONOMY DISTRIBUTION")
    print("="*80)
    blooms_counts = df['blooms_name'].value_counts()
    for level, count in blooms_counts.items():
        print(f"{level}: {count} ({count/len(df)*100:.1f}%)")
    
    print(f"\nAverage Cognitive Depth: {df['blooms_level'].mean():.2f}/6")
    
    # Detailed results
    print("\n" + "="*80)
    print("DETAILED MESSAGE ANALYSIS")
    print("="*80)
    
    for idx, row in df.iterrows():
        print(f"\n[Message {idx+1}]")
        print(f"Text: {row['message'][:100]}..." if len(row['message']) > 100 else f"Text: {row['message']}")
        print(f"  → Phase: {row['zimmerman_phase'].upper()}")
        print(f"  → COPES: {row['copes_score']}/5 (C:{row['copes_components']['C']} O:{row['copes_components']['O']} P:{row['copes_components']['P']} E:{row['copes_components']['E']} S:{row['copes_components']['S']})")
        conf = row['blooms_confidence']
        conf_val = float(conf) if conf is not None and str(conf).strip() != '' else 0.0
        print(f"  → Bloom's: Level {row['blooms_level']} - {row['blooms_name']} (confidence: {conf_val:.2f})")
    
    return df


def enhanced_critical_thinking_analysis_json(chats):
    """
    Analyzes CHATS loaded from JSON (not individual messages)
    Each chat contains multiple user messages treated as one conversation
    """
    print("\n" + "="*80)
    print("ENHANCED SRL + CRITICAL THINKING ANALYSIS (FROM CHAT HISTORY)")
    print("="*80)
    print(f"Analyzing {len(chats)} conversations")
    
    chat_results = []
    
    for i, chat in enumerate(chats):
        print(f"\nChat {i+1}/{len(chats)}: {chat['topic']}")
        print(f"  User messages: {len(chat['messages'])}")
        
        # Combine all user messages in this chat
        full_conversation = " ".join(chat['messages'])

        # Classify the entire chat
        zimmerman_phase = classify_zimmerman_phase(full_conversation)
        copes_analysis = analyze_copes_components(full_conversation, zimmerman_phase)
        blooms_result = classify_blooms_level(full_conversation)
        
        # Store results (coerce confidence to float; API may return string)
        conf_raw = blooms_result.get('confidence')
        try:
            blooms_conf = float(conf_raw) if conf_raw is not None else 0.0
        except (TypeError, ValueError):
            blooms_conf = 0.0
        chat_results.append({
            'chat_id': chat['chat_id'],
            'topic': chat['topic'],
            'updated_at': chat.get('updated_at'),
            'num_messages': chat['num_messages'],
            'zimmerman_phase': zimmerman_phase,
            'copes_score': copes_analysis['total'],
            'copes_C': copes_analysis['C'],
            'copes_O': copes_analysis['O'],
            'copes_P': copes_analysis['P'],
            'copes_E': copes_analysis['E'],
            'copes_S': copes_analysis['S'],
            'blooms_level': blooms_result['level'],
            'blooms_name': blooms_result['level_name'],
            'blooms_confidence': blooms_conf,
            'first_message': chat['messages'][0][:100] + "..." if len(chat['messages'][0]) > 100 else chat['messages'][0]
        })
        
        # Rate limiting
        if (i + 1) % 3 == 0 and i < len(chats) - 1:
            print(f"  Rate limit: Waiting 20 seconds... ({i+1}/{len(chats)} done)")
            time.sleep(20)
    
    # Convert to DataFrame
    df = pd.DataFrame(chat_results)
    
    # Statistics
    print("\n" + "="*80)
    print("ANALYSIS SUMMARY")
    print("="*80)
    print(f"Total conversations: {len(df)}")
    
    print("\n" + "="*80)
    print("ZIMMERMAN PHASE DISTRIBUTION")
    print("="*80)
    phase_counts = df['zimmerman_phase'].value_counts()
    for phase, count in phase_counts.items():
        print(f"{phase.upper()}: {count} ({count/len(df)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("COPES QUALITY SCORES")
    print("="*80)
    print(f"Average: {df['copes_score'].mean():.2f}/5")
    print(f"High Quality (4-5): {len(df[df['copes_score'] >= 4])} ({len(df[df['copes_score'] >= 4])/len(df)*100:.1f}%)")
    print(f"Low Quality (1-2): {len(df[df['copes_score'] <= 2])} ({len(df[df['copes_score'] <= 2])/len(df)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("BLOOM'S TAXONOMY DISTRIBUTION")
    print("="*80)
    blooms_counts = df['blooms_name'].value_counts()
    for level, count in blooms_counts.items():
        print(f"{level}: {count} ({count/len(df)*100:.1f}%)")
    print(f"\nAverage Cognitive Depth: {df['blooms_level'].mean():.2f}/6")
    
    # Detailed results
    print("\n" + "="*80)
    print("DETAILED CHAT ANALYSIS")
    print("="*80)
    for idx, row in df.iterrows():
        print(f"\n[Chat {idx+1}] {row['topic']}")
        print(f"  ID: {row['chat_id']}")
        print(f"  Messages: {row['num_messages']}")
        print(f"  Phase: {row['zimmerman_phase'].upper()}")
        print(f"  COPES: {row['copes_score']}/5 (C:{row['copes_C']} O:{row['copes_O']} P:{row['copes_P']} E:{row['copes_E']} S:{row['copes_S']})")
        conf = row['blooms_confidence']
        conf_val = float(conf) if conf is not None and str(conf).strip() != '' else 0.0
        print(f"  Bloom's: Level {row['blooms_level']} - {row['blooms_name']} (confidence: {conf_val:.2f})")
        print(f"  First message: {row['first_message']}")
    
    return df

# ============================================================================
# MAIN EXECUTION
# ============================================================================
if __name__ == "__main__":
    
    print("\n" + "="*80)
    print("CHAT HISTORY ANALYSIS")
    print("="*80)
    print("\nChoose analysis mode:")
    print("1. Analyze from JSON chat history file")
    print("2. Test with sample messages")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        # JSON file analysis
        json_filepath = input("\nEnter path to your chat history JSON file: ").strip()
        json_filepath = json_filepath.strip('"').strip("'")
        
        try:
            print(f"\nLoading chat history from: {json_filepath}")
            chats = load_chat_history_flexible(json_filepath)
            
            print(f"✓ Successfully loaded {len(chats)} conversations")
            print(f"✓ Total user messages: {sum(chat['num_messages'] for chat in chats)}")
            
            # Preview
            print("\n" + "="*80)
            print("PREVIEW OF LOADED CHATS")
            print("="*80)
            for i, chat in enumerate(chats[:3], 1):
                print(f"\n{i}. {chat['topic']}")
                print(f"   Messages: {chat['num_messages']}")
                print(f"   First: {chat['messages'][0][:80]}...")
            
            if len(chats) > 3:
                print(f"\n... and {len(chats) - 3} more")
            
            # Confirm
            proceed = input(f"\nAnalyze {len(chats)} conversations? (y/n): ").lower()
            
            if proceed == 'y':
                results_df = enhanced_critical_thinking_analysis_json(chats)
                
                # Save results (if needed)
                #results_df.to_csv('chat_history_analysis.csv', index=False)
                #results_df.to_json('chat_history_analysis.json', orient='records', indent=2)
                
                #print("\n" + "="*80)
                #print("✓ Results saved to 'chat_history_analysis.csv'")
                #print("✓ Results saved to 'chat_history_analysis.json'")
                #print("="*80)
            else:
                print("\nAnalysis cancelled.")
        
        except FileNotFoundError:
            print(f"\n❌ Error: File not found '{json_filepath}'")
        except json.JSONDecodeError as e:
            print(f"\n❌ Error: Invalid JSON - {e}")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    elif choice == "2":
        # Test mode with sample messages
        test_messages = [
            "I want to learn about binary search trees. I should probably start by understanding the basic structure first, then move to operations like insertion and deletion.",
            "I'm implementing a BST now. Here's my insert method - does this logic look correct for handling the left and right child pointers?",
            "Looking back at my BST implementation, I should have drawn out the tree structure on paper first. That would have helped me catch the comparison logic error faster.",
            "What's a hash table?",
            "I'm building a hash table for my project (due Friday). I've implemented insert using separate chaining, but I'm noticing O(n) worst case when chains get long. Should I rehash when load factor exceeds 0.75?",
            "Define polymorphism",
            "So polymorphism means objects can take multiple forms?",
            "I'm using polymorphism in my game engine to handle different enemy types",
            "Why does polymorphism in Python work differently than in Java given they both use inheritance?",
            "I'm designing a new architecture that combines polymorphism with composition for better flexibility",
            "Composition is better than inheritance here because it provides loose coupling and meets the SOLID principles better",
        ]
        
        print("\nStarting test analysis...")
        print(f"Analyzing {len(test_messages)} messages\n")
        
        results_df = critical_thinking_analysis(test_messages)
        # if needed results saved to file
        '''results_df.to_csv('srl_test_results.csv', index=False)
        print("\n" + "="*80)
        print("✓ Results saved to 'srl_test_results.csv'")
        print("="*80)
        '''
    else:
        print("\nInvalid choice. Exiting.")