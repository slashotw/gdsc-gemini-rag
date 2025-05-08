from flask import Flask, request, render_template_string
import google.generativeai as genai
app = Flask(__name__)
genai.configure(api_key='put your api key here')  
model = genai.GenerativeModel('gemini-1.5-flash')
HTML = '''
<form action="/" method="post">
  <input type="text" name="prompt" placeholder="輸入訊息">
  <input type="submit" value="送出">
</form>
<p>{{ response }}</p>'''
@app.route('/', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        prompt = request.form['prompt']
        response = model.generate_content(prompt).text
        return render_template_string(HTML, response=response)
    return render_template_string(HTML, response='')
if __name__ == '__main__':
    app.run(debug=True)