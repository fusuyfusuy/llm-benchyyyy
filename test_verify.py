from bench.sandbox import create
from bench.harness import configs as harness_configs, cli_adapter
sb = create([], None)
conf = harness_configs.REGISTRY["antigravity"]
print("Running verify for gpt-oss...")
try:
    res = cli_adapter.run(conf, sb, "Say OK", "gpt-oss")
    print("VERIFY RETURNED:", res)
except Exception as e:
    print("VERIFY EXCEPTION:", e)
