import sqlite3
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch
import re


def generate_questions(topic):
    model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id)

    generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=0 if torch.cuda.is_available() else -1
    )

    prompt = f"""Generate 5 trivia questions about the topic: {topic}
    Follow this format exactly:

    Question #1: What is the capital of France?
     a) Paris
     b) London
     c) Berlin
     d) Madrid

    Now generate the rest:"""

    output = generator(
        prompt,
        max_new_tokens=3000,
        temperature=0.8,
        top_p=0.92,
        top_k=50,
        do_sample=True,
        num_return_sequences=1,
        repetition_penalty=1.15,
        length_penalty=1.1,
        no_repeat_ngram_size=4,
        early_stopping=True
    )[0]["generated_text"]

    return parse_generated_questions(output.strip(), topic)


def parse_generated_questions(raw_text, category):
    questions = []
    pattern = re.compile(
        r'Question #\d+:(.*?)\n\s*a\)\s*(.*?)\n\s*b\)\s*(.*?)\n\s*c\)\s*(.*?)\n\s*d\)\s*(.*?)(?=\nQuestion #\d+:|\Z)',
        re.DOTALL)
    matches = pattern.findall(raw_text)

    for match in matches:
        question, correct, wrong1, wrong2, wrong3 = map(str.strip, match)
        questions.append((question, correct, wrong1, wrong2, wrong3, category))

    return questions


def insert_generated_questions(questions):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.executemany(
        'INSERT INTO questions (question, correct, wrong1, wrong2, wrong3, category) VALUES (?, ?, ?, ?, ?, ?)',
        questions)
    conn.commit()
    conn.close()

class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quiz App")
        self.root.geometry("640x480")

        # edit theme
        style = ttk.Style()
        style.theme_use('clam')

        # edit font
        self.title_font = ("Helvetica", 16, "bold")
        self.default_font = ("Arial", 12)

        # Top part of window (search bar, create quiz)
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        self.search_label = ttk.Label(top_frame, text="Search Quiz:", font=self.default_font)
        self.search_label.pack(side=tk.LEFT, padx=5)

        self.search_entry = ttk.Entry(top_frame, font=self.default_font, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)

        self.search_button = ttk.Button(top_frame, text="Search", command=self.search_quizzes)
        self.search_button.pack(side=tk.LEFT, padx=5)

        self.create_quiz_button = ttk.Button(top_frame, text="Create New Quiz", command=self.create_new_quiz)
        self.create_quiz_button.pack(side=tk.LEFT, padx=5)

        # Search results
        results_frame = ttk.LabelFrame(self.root, text="Available Quizzes", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.result_listbox = tk.Listbox(results_frame, font=self.default_font, height=12)
        self.result_listbox.pack(fill=tk.BOTH, expand=True)
        self.result_listbox.bind("<Double-1>", self.load_selected_quiz)

        self.create_database()  #

        generate_button = ttk.Button(top_frame, text="Generate Quiz", command=self.open_generate_window)
        generate_button.pack(side=tk.LEFT, padx=5)

    def create_database(self):
        """ Creates the database with some placeholder quizzes. """
        conn = sqlite3.connect("quiz.db")
        c = conn.cursor()

        # Quizzes table
        c.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL
        )''')

        # Questions table
        c.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT,'
                  ' quiz_id INTEGER, question TEXT NOT NULL, correct TEXT NOT NULL,'
                  ' wrong1 TEXT NOT NULL, wrong2 TEXT NOT NULL, wrong3 TEXT NOT NULL,'
                  ' category TEXT, FOREIGN KEY(quiz_id) REFERENCES quizzes(id))')

        conn.commit()
        conn.close()

    def search_quizzes(self):
        query = self.search_entry.get().lower()
        conn = sqlite3.connect("quiz.db")
        c = conn.cursor()
        c.execute("SELECT id, topic FROM quizzes WHERE LOWER(topic) LIKE ?", (f"%{query}%",))
        results = c.fetchall()
        conn.close()

        self.result_listbox.delete(0, tk.END)
        for quiz_id, topic in results:
            self.result_listbox.insert(tk.END, f"{quiz_id}: {topic}")

    def open_generate_window(self):
        top = tk.Toplevel(self.root)
        top.title("Generate Quiz")
        top.geometry("400x200")

        label = tk.Label(top, text="Enter quiz topic:")
        label.pack(pady=10)

        topic_entry = tk.Entry(top, width=40)
        topic_entry.pack(pady=5)

        def on_submit():
            topic = topic_entry.get()
            if topic.strip():
                try:
                    questions = generate_questions(topic)
                    insert_generated_questions(questions)
                    messagebox.showinfo("Success", f"Generated and inserted {len(questions)} questions on '{topic}'.")
                    top.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to generate questions: {str(e)}")

        submit_btn = tk.Button(top, text="Generate", command=on_submit)
        submit_btn.pack(pady=10)

    def load_selected_quiz(self, event):
        selection = self.result_listbox.curselection()
        if not selection:
            return

        selected_text = self.result_listbox.get(selection[0])
        quiz_id = int(selected_text.split(":")[0])

        mode = messagebox.askquestion("Select Mode", "Use Quiz Mode? (No = Flashcards)")

        if mode == 'yes':
            self.launch_quiz_mode(quiz_id)
        else:
            self.launch_flashcard_mode(quiz_id)



    def launch_quiz_mode(self, quiz_id):
        quiz_window = tk.Toplevel(self.root)
        quiz_window.title("Quiz Mode")
        quiz_window.geometry("600x400")

        conn = sqlite3.connect("quiz.db")
        c = conn.cursor()
        c.execute("SELECT question, correct, wrong1, wrong2, wrong3 FROM questions WHERE quiz_id = ?", (quiz_id,))
        self.questions = c.fetchall()
        conn.close()

        self.q_index = 0
        self.score = 0

        def next_question():
            nonlocal radio_var
            if radio_var.get() == self.questions[self.q_index][5]:
                self.score += 1
            self.q_index += 1
            if self.q_index < len(self.questions):
                update_question()
            else:
                messagebox.showinfo("Quiz Finished", f"Your score: {self.score} / {len(self.questions)}")
                quiz_window.destroy()

        def update_question():
            question, a, b, c, d, _ = self.questions[self.q_index]
            question_label.config(text=question)
            radio_var.set(None)
            for i, val in enumerate([a, b, c, d]):
                radio_buttons[i].config(text=val, value=val)

        question_label = ttk.Label(quiz_window, text="", font=self.default_font, wraplength=500)
        question_label.pack(pady=10)

        radio_var = tk.StringVar()
        radio_buttons = []
        for _ in range(4):
            rb = ttk.Radiobutton(quiz_window, text="", variable=radio_var, value="", style="TRadiobutton")
            rb.pack(anchor=tk.W, padx=20, pady=2)
            radio_buttons.append(rb)

        next_btn = ttk.Button(quiz_window, text="Next", command=next_question)
        next_btn.pack(pady=10)

        update_question()

    def launch_flashcard_mode(self, quiz_id):
        flash_window = tk.Toplevel(self.root)
        flash_window.title("Flashcard Mode")
        flash_window.geometry("500x300")

        conn = sqlite3.connect("quiz.db")
        c = conn.cursor()
        c.execute("SELECT question, correct FROM questions WHERE quiz_id = ?", (quiz_id,))
        flashcards = c.fetchall()
        conn.close()

        index = 0
        show_answer = False

        def toggle_card():
            nonlocal show_answer
            show_answer = not show_answer
            if show_answer:
                card_label.config(text=flashcards[index][1])
                flip_button.config(text="Show Question")
            else:
                card_label.config(text=flashcards[index][0])
                flip_button.config(text="Show Answer")

        def next_card():
            nonlocal index, show_answer
            index = (index + 1) % len(flashcards)
            show_answer = False
            card_label.config(text=flashcards[index][0])
            flip_button.config(text="Show Answer")

        card_label = ttk.Label(flash_window, text=flashcards[index][0], font=self.default_font, wraplength=400, justify="center")
        card_label.pack(pady=30)

        flip_button = ttk.Button(flash_window, text="Reveal Answer", command=toggle_card)
        flip_button.pack(pady=5)

        next_button = ttk.Button(flash_window, text="Next Card", command=next_card)
        next_button.pack(pady=5)

    def create_new_quiz(self):
        create_window = tk.Toplevel(self.root)
        create_window.title("Create New Quiz")
        create_window.geometry("600x600")

        topic_label = ttk.Label(create_window, text="Quiz Topic:", font=self.default_font)
        topic_label.pack(pady=5)

        topic_entry = ttk.Entry(create_window, font=self.default_font, width=40)
        topic_entry.pack(pady=5)

        questions_frame = ttk.Frame(create_window)
        questions_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        questions_list = []

        def add_question():
            q_text = question_entry.get()
            a = entry_a.get()
            b = entry_b.get()
            c = entry_c.get()
            d = entry_d.get()
            correct = correct_var.get()

            if not all([q_text, a, b, c, d, correct]):
                messagebox.showerror("Error", "Please fill out all fields and select a correct answer.")
                return

            questions_list.append((q_text, a, b, c, d, correct))

            question_entry.delete(0, tk.END)
            entry_a.delete(0, tk.END)
            entry_b.delete(0, tk.END)
            entry_c.delete(0, tk.END)
            entry_d.delete(0, tk.END)
            correct_var.set("")

            messagebox.showinfo("Continue", "Question added. Add more or click Save Quiz when done.",
                                parent=create_window)

        def save_quiz():
            topic = topic_entry.get()
            if not topic or not questions_list:
                messagebox.showerror("Error", "Enter a topic and at least one question.")
                return

            conn = sqlite3.connect("quiz.db")
            c = conn.cursor()
            c.execute("INSERT INTO quizzes (topic) VALUES (?)", (topic,))
            quiz_id = c.lastrowid

            for q in questions_list:
                c.execute('''
                          INSERT INTO questions (quiz_id, question, correct, wrong1, wrong2, wrong3, category)
                          VALUES (?, ?, ?, ?, ?, ?, ?)
                          ''', (quiz_id, *q))

            conn.commit()
            conn.close()
            create_window.destroy()
            messagebox.showinfo("Success", "Quiz created successfully!")
            self.search_quizzes()

        question_entry = ttk.Entry(questions_frame, font=self.default_font, width=50)
        question_entry.pack(pady=5)
        entry_a = ttk.Entry(questions_frame, font=self.default_font, width=50)
        entry_a.pack(pady=5)
        entry_b = ttk.Entry(questions_frame, font=self.default_font, width=50)
        entry_b.pack(pady=5)
        entry_c = ttk.Entry(questions_frame, font=self.default_font, width=50)
        entry_c.pack(pady=5)
        entry_d = ttk.Entry(questions_frame, font=self.default_font, width=50)
        entry_d.pack(pady=5)

        correct_var = tk.StringVar()
        correct_label = ttk.Label(questions_frame, text="Correct Answer:", font=self.default_font)
        correct_label.pack()
        correct_dropdown = ttk.Combobox(questions_frame, textvariable=correct_var, values=["A", "B", "C", "D"], font=self.default_font, state="readonly")
        correct_dropdown.pack(pady=5)

        add_btn = ttk.Button(questions_frame, text="Add Question", command=add_question)
        add_btn.pack(pady=5)

        save_btn = ttk.Button(questions_frame, text="Save Quiz", command=save_quiz)
        save_btn.pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()
