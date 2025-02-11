import time
import asyncio
import argparse
from playwright.async_api import async_playwright

class GPT:
    def __init__(self, prompt, streaming=True, proxy=None):
        self.prompt = prompt
        self.streaming = streaming
        self.proxy = proxy
        self.browser = None
        self.page = None
        self.session_active = True
        self.last_message_id = None

    async def start(self):
        async with async_playwright() as p:
            launch_options = {'headless': True}
            if self.proxy:
                launch_options['proxy'] = {
                    'server': self.proxy
                }
            self.browser = await p.firefox.launch(**launch_options)
            context_options = {
                'user_agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1"
            }
            context = await self.browser.new_context(**context_options)
            self.page = await context.new_page()
            await self.page.goto('https://chat.openai.com', wait_until='networkidle')
            await self.handle_prompt(self.prompt)

            while self.session_active:
                next_prompt = input("\n►: ")
                if next_prompt.lower() == 'exit':
                    self.session_active = False
                    break
                await self.handle_prompt(next_prompt)

    async def handle_prompt(self, prompt_text):
        prompt_textarea = await self.page.query_selector('#prompt-textarea')
        if prompt_textarea is None:
            print("Cannot find the prompt input on the webpage.\nPlease check whether you have access to chat.openai.com without logging in via your browser.")
            self.session_active = False
            await self.close()
            return 
        
        await self.page.type('#prompt-textarea', prompt_text, delay=100)
        
        try:
            await self.page.click('[data-testid="send-button"]')
        except Exception as e:
            print(f"Failed to click the send button: {str(e)}")
        
        await self.wait_for_and_print_new_response()

    async def wait_for_and_print_new_response(self):
        await self.wait_for_initial_response()
        await self.handle_streaming_response()

    async def wait_for_initial_response(self):
        start_time = time.time()
        timeout = 30
        while (time.time() - start_time) < timeout:
            assistant_messages = await self.page.query_selector_all('div[data-message-author-role="assistant"]')
            if assistant_messages:
                last_message = assistant_messages[-1]
                is_thinking = await last_message.query_selector('.result-thinking')
                if not is_thinking:
                    self.last_message_id = await self.page.evaluate('(element) => element.getAttribute("data-message-id")', last_message)
                    return
            await asyncio.sleep(0.1)
        print("Timed out waiting for the initial response.")

    async def handle_streaming_response(self):
        previous_text = ""
        complete_response = ""
        new_content_detected = False
        while not new_content_detected:
            assistant_messages = await self.page.query_selector_all('div[data-message-author-role="assistant"]')
            if assistant_messages:
                last_message = assistant_messages[-1]
                current_message_id = await self.page.evaluate('(element) => element.getAttribute("data-message-id")', last_message)
                
                if current_message_id == self.last_message_id:
                    current_text = await self.page.evaluate('(element) => element.textContent', last_message)
                    if current_text != previous_text:
                        if self.streaming:
                            print(current_text[len(previous_text):], end='', flush=True)
                        else:
                            complete_response += current_text[len(previous_text):]

                    previous_text = current_text
                    is_streaming = await last_message.query_selector('.result-streaming')
                    if not is_streaming:
                        new_content_detected = True
                else:
                    self.last_message_id = current_message_id
            await asyncio.sleep(0.1)
        
        if not self.streaming:
            print(complete_response.rstrip())

    async def close(self):
        await self.page.close()
        await self.browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ChatGPT without login')
    parser.add_argument('-p', '--prompt', type=str, default="Hello, GPT", help='The initial prompt text to send to ChatGPT')
    parser.add_argument('-x', '--proxy', type=str, help='Proxy server to use, e.g. http://proxyserver:port')
    parser.add_argument('-ns', '--no-streaming', dest='streaming', action='store_false', help='Disable streaming of ChatGPT responses')
    args = parser.parse_args()

    async def main():
        session = GPT(args.prompt, args.streaming, args.proxy)
        try:
            await session.start()
        except KeyboardInterrupt:
            print("Interrupted by user, closing...")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await session.close()

    asyncio.run(main())
