import ebooklib
from ebooklib import epub
import bs4

def slice_epub(input_path, start_chapter=1312, output_file="novel_rest.txt"):
    book = epub.read_epub(input_path)
    chapters_found = 0
    remaining_text = []

    # Iterate through the items in the EPUB
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Convert HTML content to clean text
            soup = bs4.BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text()
            
            # This is a simple logic: we check for the word 'Chapter' 
            # or you can adjust this based on how the book is formatted
            if "Chapter" in text or "CHAPTER" in text:
                chapters_found += 1
            
            # Only start saving text once we hit your target chapter
            if chapters_found >= start_chapter:
                remaining_text.append(text)

    # Save the remaining part of the book
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(remaining_text))
    
    print(f"Done! Saved content from Chapter {start_chapter} onwards to {output_file}")

slice_epub("The Hanged Man - LotM Vol. 7.epub")