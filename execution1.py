import os
from spire.pdf.common import *
from spire.pdf import *

def has_file_with_extension(directory, extension):
    for filename in os.listdir(directory):
        if filename.endswith(extension):
            return True
    return False
    
def modify(str):
    a = str.find("<body style='margin:0'>")
    str = "{% extends 'base_read.html' %}\n{% block content %}\n<div class='left-right-content'>\n<div></div>\n<div class='center-content'>" + str[a+23:]
    a = str.find("</html>")
    str = str[:a - 9] + "</div></div>\n{% endblock %}"
    return str

def check_file_exists(file_path):
    return os.path.exists(file_path)

def PDF2HTML(pdf_pathway, html_pathway):
    if check_file_exists(pdf_pathway):
        doc = PdfDocument()
        doc.LoadFromFile(pdf_pathway)
        convertOptions = doc.ConvertOptions
        convertOptions.SetPdfToHtmlOptions(True, True, 1, True)
        try:
            doc.SaveToFile(html_pathway, FileFormat.HTML)
        except Exception as e:
            return e
        doc.Dispose()

        with open(html_pathway, 'r', encoding='utf-8') as file:
            html_content = file.read()
        processed_html_content = html_content
        a = processed_html_content.find('<g>\n\t\t\t<text style="fill:#FF0000')
        while a != -1:
            replace_content = processed_html_content[a:a+235]
            processed_html_content = processed_html_content.replace(replace_content, "")
            a = processed_html_content.find('<g>\n\t\t\t<text style="fill:#FF0000')

        a = processed_html_content.find('width="793" height="1121"')
        while a != -1:
            replace_content = processed_html_content[a:a + 25]
            #print(replace_content)
            processed_html_content = processed_html_content.replace(replace_content, ' viewBox="0 0 793 1121" ')
            a = processed_html_content.find('width="793" height="1121"')

        processed_html_content = modify(processed_html_content)
        
        with open(html_pathway, 'w', encoding='utf-8') as file:
            file.write(processed_html_content)
        file.close()
        
        return "Success!"

    else:
        return "File Not Found"

pathway = str(os.getcwd().replace("\\", "/").lower()) + "/templates/reads/"

for folder in os.listdir(pathway):
    if not has_file_with_extension(pathway + folder, '.html'):
        for file in os.listdir(pathway + folder):
            if file.endswith(".pdf"):
                pdf_pathway = pathway + folder + "/" + file
                html_pathway = pathway + folder + "/" + file[:-4] + ".html"
                break
        print(PDF2HTML(pdf_pathway, html_pathway))
    else:
        pass
