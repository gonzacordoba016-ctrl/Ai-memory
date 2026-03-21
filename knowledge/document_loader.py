# knowledge/document_loader.py

import os


def load_text_file(path):

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_documents(folder_path):

    documents = []

    for root, _, files in os.walk(folder_path):

        for file in files:

            if file.endswith(".txt") or file.endswith(".md"):

                full_path = os.path.join(root, file)

                text = load_text_file(full_path)

                documents.append({
                    "source": file,
                    "content": text
                })

    return documents