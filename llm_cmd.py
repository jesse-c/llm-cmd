import click
import llm
import subprocess
import shutil
from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from pygments.lexers.shell import BashLexer

SYSTEM_PROMPT = """
Return only the command to be executed as a raw string, no string delimiters
wrapping it, no yapping, no markdown, no fenced code blocks, what you return
will be passed to subprocess.check_output() directly.
For example, if the user asks: undo last git commit
You return only: git reset --soft HEAD~1
""".strip()


@llm.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument("args", nargs=-1)
    @click.option("-m", "--model", default=None, help="Specify the model to use")
    @click.option("-s", "--system", help="Custom system prompt")
    @click.option("--key", help="API key to use")
    @click.option("--tldr", is_flag=True, default=False, help="Enrich with TLDR data")
    def cmd(args, model, system, key, tldr):
        """Generate and execute commands in your shell"""
        from llm.cli import get_default_model

        prompt = " ".join(args)
        model_id = model or get_default_model()
        model_obj = llm.get_model(model_id)
        if model_obj.needs_key:
            model_obj.key = llm.get_key(key, model_obj.needs_key, model_obj.key_env_var)
        result = model_obj.prompt(prompt, system=system or SYSTEM_PROMPT)
        result_str = str(result)
        print("result_str")
        print(result_str)

        if tldr and shutil.which("tldr"):
            # Extract the first word from the result as the command and remove any backticks
            command = result_str.strip().split()[0].strip("`")
            print("command")
            print(command)

            # First try updating the tldr cache
            try:
                subprocess.run(["tldr", "--update"], capture_output=True, text=True)
            except subprocess.SubprocessError:
                pass

            try:
                tldr_output = subprocess.run(
                    ["tldr", command], capture_output=True, text=True
                )
                print(tldr_output)
                if tldr_output.returncode == 0:
                    # Re-prompt with the TLDR information
                    enriched_prompt = f"{prompt}\n\nHere's examples for `{command}`:\n{tldr_output.stdout}. You only return the terminal command. Don't include backticks."
                    print(enriched_prompt)
                    result = model_obj.prompt(
                        enriched_prompt, system=system or SYSTEM_PROMPT
                    )
                    result_str = str(result)
            except subprocess.SubprocessError:
                pass  # Silently continue if tldr fails

        interactive_exec(result_str)


def interactive_exec(command):
    session = PromptSession(lexer=PygmentsLexer(BashLexer))
    with patch_stdout():
        if "\n" in command:
            print("Multiline command - Meta-Enter or Esc Enter to execute")
            edited_command = session.prompt("> ", default=command, multiline=True)
        else:
            edited_command = session.prompt("> ", default=command)
    try:
        output = subprocess.check_output(
            edited_command, shell=True, stderr=subprocess.STDOUT
        )
        print(output.decode())
    except subprocess.CalledProcessError as e:
        print(
            f"Command failed with error (exit status {e.returncode}): {e.output.decode()}"
        )
