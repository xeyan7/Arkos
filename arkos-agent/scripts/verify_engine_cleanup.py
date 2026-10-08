"""Offline embedding regressions. Run with Python 3.11-3.13 and engine dependencies installed."""
import os, sys, tempfile, pathlib, unittest, importlib, json, socket
from decimal import Decimal
from unittest.mock import patch, Mock
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
workspace = pathlib.Path(os.environ.get('ARKOS_TEST_TMP', str(ROOT.parent))).resolve()
with tempfile.TemporaryDirectory(prefix='arkos-provider-check-', dir=workspace) as tmp:
    assert pathlib.Path(tmp).resolve().is_relative_to(workspace)
    os.environ['ARKOS_HOME'] = tmp
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['ARKOS_DISABLE_AUTO_INSTALL'] = '1'
    for k in list(os.environ):
        if k.endswith(('_API_KEY', '_TOKEN', '_TOKEN_SECRET', '_TOKEN_ID')):
            os.environ.pop(k, None)

    real_connect = socket.socket.connect

    def no_network(sock, address, *args, **kwargs):
        import ipaddress
        if isinstance(address, tuple):
            try:
                if ipaddress.ip_address(address[0]).is_loopback:
                    return real_connect(sock, address, *args, **kwargs)
            except ValueError:
                pass
        raise AssertionError('Unexpected external network request')
    with patch.object(socket.socket, 'connect', no_network), patch.object(pathlib.Path, 'home', return_value=pathlib.Path(tmp)):

        class ProviderRegression(unittest.TestCase):

            def test_provider_discovery_and_runtime(self):
                from providers import list_providers
                from arkos_cli import auth
                from arkos_cli.runtime_provider import resolve_runtime_provider
                names = {p.name for p in list_providers()}
                self.assertTrue({'openrouter', 'minimax-oauth', 'qwen-oauth', 'anthropic'} <= names)
                self.assertNotIn('portal', names)
                self.assertNotIn('portal', auth.PROVIDER_REGISTRY)
                self.assertTrue(auth.PROVIDER_REGISTRY['minimax-oauth'].extra['cn_portal_base_url'])
                runtime = resolve_runtime_provider(requested='openai-api', explicit_api_key='test-key', explicit_base_url='https://api.openai.com/v1', target_model='gpt-4o-mini')
                self.assertEqual(runtime['provider'], 'openai-api')
                with self.assertRaises(auth.AuthError):
                    resolve_runtime_provider(requested='portal', explicit_api_key='test-key')

            def test_tool_setup(self):
                from arkos_cli.tool_configuration import TOOL_CATEGORIES
                from arkos_cli.tool_providers import _visible_providers, _write_provider_config
                for cat in TOOL_CATEGORIES.values():
                    rows = _visible_providers(cat, {})
                    self.assertFalse(any(('portal' in str(r).lower() for r in rows)))
                c = {'tts': {'use_gateway': True}}
                _write_provider_config({'tts_provider': 'openai'}, c)
                self.assertEqual(c['tts'], {'provider': 'openai'})
                for row, section, key in [({'browser_provider': 'browser-use'}, 'browser', 'cloud_provider'), ({'web_backend': 'firecrawl'}, 'web', 'backend')]:
                    c = {}
                    _write_provider_config(row, c)
                    self.assertEqual(c[section][key], next(iter(row.values())))

            def test_billing_and_pricing(self):
                from agent.billing_links import build_billing_block
                from agent.usage_pricing import estimate_usage_cost, CanonicalUsage, PricingEntry
                link = build_billing_block(provider='openai-api', base_url='https://api.openai.com/v1', model='gpt-4o-mini')
                self.assertIn('platform.openai.com', link.billing_url)
                self.assertNotIn('is_portal', link.to_dict())
                entry = PricingEntry(input_cost_per_million=Decimal('2'), output_cost_per_million=Decimal('8'), cache_read_cost_per_million=Decimal('0.5'), cache_write_cost_per_million=Decimal('2.5'), source='official_docs_snapshot')
                with patch('agent.usage_pricing.get_pricing_entry', return_value=entry):
                    cost = estimate_usage_cost('gpt-test', CanonicalUsage(input_tokens=1000, output_tokens=200, cache_read_tokens=500, cache_write_tokens=100), provider='openai-api')
                self.assertEqual(cost.amount_usd, Decimal('0.00410'))
                included = estimate_usage_cost('gpt-5', CanonicalUsage(input_tokens=100), provider='openai-codex')
                self.assertEqual(included.status, 'included')
                with patch('agent.usage_pricing.get_pricing_entry', return_value=None):
                    self.assertEqual(estimate_usage_cost('unknown', CanonicalUsage(input_tokens=1), provider='custom').status, 'unknown')

            def test_request_context(self):
                from agent.request_context import set_conversation_context, reset_conversation_context, get_conversation_context, set_affinity_scope, reset_affinity_scope, get_affinity_scope
                t = set_conversation_context('conversation')
                s = set_affinity_scope('profile')
                self.assertEqual(get_conversation_context(), 'conversation')
                self.assertEqual(get_affinity_scope(), 'profile')
                reset_conversation_context(t)
                reset_affinity_scope(s)
                self.assertIsNone(get_conversation_context())

            def test_direct_audio_and_vendor_routes(self):
                import tools.web_tools
                from tools import tts_tool_openai, transcription_cloud
                from plugins.browser.browser_use.provider import BrowserUseBrowserProvider
                import plugins.image_gen.krea as krea
                with patch('tools.tool_backend_helpers.resolve_openai_audio_api_key', return_value='test-key'):
                    self.assertEqual(tts_tool_openai._resolve_openai_audio_client_config()[0], 'test-key')
                    self.assertEqual(transcription_cloud._resolve_openai_audio_client_config()[0], 'test-key')
                self.assertEqual(krea._headers('test-key', json_body=True)['Authorization'], 'Bearer test-key')
                p = BrowserUseBrowserProvider()
                response = Mock(ok=True)
                response.json.return_value = {'id': 'test', 'cdpUrl': 'wss://example'}
                with patch.object(p, '_get_config', return_value={'api_key': 'test-key', 'base_url': 'https://api.browser-use.com/api/v3'}), patch.object(p, '_post_create', return_value=response) as create:
                    result = p.create_session('task')
                    self.assertEqual(result['bb_session_id'], 'test')
                    self.assertEqual(create.call_args.args[2], {})

            def test_state_storage(self):
                from arkos_state import SessionDB
                db = SessionDB(pathlib.Path(tmp) / 'test-state.db')
                try:
                    db.create_session('s1', 'cli', model='gpt-4o-mini')
                    db.create_session('s2', 'cli', parent_session_id='s1')
                    db.update_token_counts('s1', input_tokens=100, output_tokens=20, estimated_cost_usd=0.0041, cost_status='estimated', billing_provider='openai-api', api_call_count=1)
                    self.assertEqual(db.get_session('s1')['input_tokens'], 100)
                    self.assertEqual(db.get_conversation_root('s2'), 's1')
                finally:
                    db.close()

            def test_agent_initialization(self):
                from run_agent import AIAgent
                with patch('agent.model_metadata.fetch_model_metadata', return_value=None):
                    agent = AIAgent(provider='openai-api', model='gpt-4o-mini', api_key='test-key', base_url='https://api.openai.com/v1', enabled_toolsets=[], quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True, save_trajectories=False)
                self.assertEqual(agent.provider, 'openai-api')
                self.assertFalse(hasattr(agent, '_credits_state'))

            def test_headless_approval_and_sudo(self):
                import builtins
                from tools.approval_prompt import prompt_dangerous_approval
                from tools.terminal_tool_sudo import _prompt_for_sudo_password
                with patch.object(builtins, 'input', side_effect=AssertionError('terminal input forbidden')):
                    self.assertEqual(prompt_dangerous_approval('rm file', 'remove file', timeout_seconds=1), 'deny')
                    cb = Mock(return_value='once')
                    self.assertEqual(prompt_dangerous_approval('rm file', 'remove file', approval_callback=cb, allow_session=False, allow_permanent=False), 'once')
                    self.assertEqual(cb.call_args.kwargs, {'allow_permanent': False, 'allow_session': False})
                    with patch('tools.terminal_tool._get_sudo_password_callback', return_value=None):
                        self.assertEqual(_prompt_for_sudo_password(), '')

            def test_tool_roundtrip_and_prompt_cache(self):
                from run_agent import AIAgent
                from openai.types.chat import ChatCompletion
                import copy, types
                requests = []

                def create(**kwargs):
                    requests.append(copy.deepcopy(kwargs))
                    msg = {'role': 'assistant', 'content': 'Done.'}
                    finish = 'stop'
                    if len(requests) == 1:
                        msg = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_todo', 'type': 'function', 'function': {'name': 'tool_call', 'arguments': json.dumps({'name': 'todo_list', 'arguments': {'todos': [{'id': '1', 'content': 'Check engine', 'status': 'completed'}]}})}}]}
                        finish = 'tool_calls'
                    return ChatCompletion.model_validate({'id': 'offline-response', 'object': 'chat.completion', 'created': 1, 'model': 'gpt-4o-mini', 'choices': [{'index': 0, 'message': msg, 'finish_reason': finish}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}})
                client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)), close=lambda: None)
                with patch('agent.model_metadata.fetch_model_metadata', return_value=None):
                    agent = AIAgent(provider='openai-api', model='gpt-4o-mini', api_key='test-key', base_url='https://api.openai.com/v1', enabled_toolsets=['todo'], quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True, save_trajectories=False)
                agent._disable_streaming = True
                agent.api_mode = 'chat_completions'
                with patch.object(agent, '_create_request_openai_client', return_value=client):
                    result = agent.run_conversation('Record that the engine was checked.')
                self.assertEqual(result.get('final_response'), 'Done.', result)
                self.assertEqual(len(requests), 2)
                self.assertEqual(requests[0]['messages'][0], requests[1]['messages'][0])
                self.assertEqual([m['role'] for m in requests[1]['messages']], ['system', 'user', 'assistant', 'tool'])
                self.assertIn('Check engine', requests[1]['messages'][-1]['content'])

            def test_host_only_oauth_and_delegation(self):
                from agent.anthropic_credentials import run_arkos_oauth_login_pure
                from tools.delegate_tool_progress import _build_child_progress_callback
                from types import SimpleNamespace
                with self.assertRaises(ValueError):
                    run_arkos_oauth_login_pure()
                cb = Mock()
                parent = SimpleNamespace(tool_progress_callback=cb)
                relay = _build_child_progress_callback(0, 'Check engine', parent, subagent_id='child', parent_id='parent', depth=1, model='test', toolsets=['todo'], session_ref={'session_id': 'child-session'})
                self.assertIsNotNone(relay)
                relay('subagent.start', preview='Starting')
                self.assertEqual(cb.call_args.args[0], 'subagent.start')
                self.assertEqual(cb.call_args.kwargs['subagent_id'], 'child')
                self.assertEqual(cb.call_args.kwargs['child_session_id'], 'child-session')

            def test_configuration_roundtrip_and_legacy_version(self):
                from arkos_cli.config import get_config_path, save_config, load_config, migrate_config, DEFAULT_CONFIG, redact_key
                p = get_config_path()
                original = p.read_bytes() if p.exists() else None
                try:
                    save_config({"agent": {"max_turns": 37}, "_config_version": DEFAULT_CONFIG["_config_version"]})
                    self.assertEqual(load_config()["agent"]["max_turns"], 37)
                    self.assertEqual(migrate_config(quiet=True)["warnings"], [])
                    save_config({"_config_version": 1})
                    result = migrate_config(quiet=True)
                    self.assertTrue(any("stored version is unchanged" in x for x in result["warnings"]))
                    self.assertEqual(json.loads(json.dumps(__import__("yaml").safe_load(p.read_text())))["_config_version"], 1)
                    self.assertNotIn("example-secret", redact_key("example-secret"))
                    self.assertEqual(redact_key(""), "(not set)")
                finally:
                    if original is None:
                        p.unlink(missing_ok=True)
                    else:
                        p.write_bytes(original)

            def test_custom_model_catalog_cache(self):
                from arkos_cli.models import cached_fetch_api_models
                from arkos_cli.model_catalog_types import NativeModelCatalog
                for suffix, catalog in [("populated", ["engine-model"]), ("empty", NativeModelCatalog())]:
                    fetch = Mock(return_value=catalog)
                    url = "https://" + suffix + ".invalid/v1"
                    first = cached_fetch_api_models("test-key", url, fetch_models=fetch)
                    second = cached_fetch_api_models("test-key", url, fetch_models=fetch)
                    self.assertEqual(first, catalog)
                    self.assertEqual(second, catalog)
                    fetch.assert_called_once()
                    if isinstance(catalog, NativeModelCatalog):
                        self.assertIsInstance(second, NativeModelCatalog)

            def test_toolset_configuration_validation(self):
                from arkos_cli.toolset_validation import validate_platform_toolsets
                from arkos_cli.toolset_scope import toolset_allowed_for_platform
                from toolsets import validate_toolset
                selections = {"cli": ["file", "terminal", "engine-missing-toolset"]}
                warnings = validate_platform_toolsets(selections, validate_toolset, toolset_allowed_for_platform)
                self.assertTrue(any("engine-missing-toolset" in warning for warning in warnings))
                self.assertEqual(selections["cli"], ["file", "terminal", "engine-missing-toolset"])
                self.assertEqual(validate_platform_toolsets({"cli": ["file"]}, validate_toolset, toolset_allowed_for_platform), [])

            def test_real_file_and_terminal_dispatch(self):
                from model_tools import handle_function_call
                from tools.terminal_tool_lifecycle import cleanup_vm
                file = pathlib.Path(tmp) / "engine-check.txt"
                task = "engine-filesystem-test"
                try:
                    with patch.dict(os.environ, {"TERMINAL_CWD": tmp, "TERMINAL_ENV": "local"}):
                        wrote = json.loads(handle_function_call("write_file", {"path": str(file), "content": "engine-check\n"}, task_id=task))
                        self.assertFalse(wrote.get("error"), wrote)
                        self.assertEqual(file.read_text(), "engine-check\n")
                        read = json.loads(handle_function_call("read_file", {"path": str(file)}, task_id=task))
                        self.assertIn("engine-check", json.dumps(read))
                        shell = json.loads(handle_function_call("terminal", {"command": "echo engine-terminal-check"}, task_id=task))
                        self.assertIn("engine-terminal-check", json.dumps(shell))
                        self.assertFalse(shell.get("error"), shell)
                        self.assertEqual(shell["exit_code"], 0, shell)
                finally:
                    cleanup_vm(task)

            def test_native_plugin_registration_and_dispatch(self):
                from arkos_cli.plugins import discover_plugins, get_plugin_manager
                from model_tools import handle_function_call
                directory = pathlib.Path(tmp) / "plugins" / "engine-health-fixture"
                directory.mkdir(parents=True)
                (directory / "plugin.yaml").write_text("name: engine-health-fixture\nversion: 1.0.0\ndescription: Offline engine integration fixture.\n")
                (directory / "__init__.py").write_text(
                    "import json\ndef register(ctx):\n"
                    "    ctx.register_tool(name='engine_health_probe', toolset='engine_health_probe', "
                    "schema={'name':'engine_health_probe','description':'Echo fixture data.',"
                    "'parameters':{'type':'object','properties':{'value':{'type':'string'}}}}, "
                    "handler=lambda args, **kw: json.dumps({'echo':args.get('value')}))\n"
                )
                from arkos_cli.config import get_config_path, save_config
                config_path = get_config_path()
                old_config = config_path.read_bytes() if config_path.exists() else None
                try:
                    save_config({"plugins": {"enabled": ["engine-health-fixture"]}})
                    discover_plugins(force=True)
                    result = json.loads(handle_function_call("engine_health_probe", {"value": "engine-plugin-check"}))
                    self.assertIn("echo", result, result)
                    self.assertEqual(result["echo"], "engine-plugin-check", result)
                finally:
                    get_plugin_manager().unload("engine-health-fixture")
                    import shutil
                    shutil.rmtree(directory)
                    if old_config is None:
                        config_path.unlink(missing_ok=True)
                    else:
                        config_path.write_bytes(old_config)

            def test_cron_storage_and_script_execution(self):
                from cron.jobs import create_job, get_job, remove_job
                from cron.scheduler import run_job
                script = pathlib.Path(tmp) / "scripts" / "engine_scheduled_check.py"
                script.parent.mkdir(exist_ok=True)
                script.write_text("print('engine-scheduled-check')\n")
                job = create_job(prompt="", schedule="every 5m", name="Engine offline check", script=str(script), no_agent=True, deliver="local")
                try:
                    self.assertTrue(get_job(job["id"])["no_agent"])
                    result = run_job(job)
                    self.assertTrue(result[0], result)
                    self.assertIn("engine-scheduled-check", result[1])
                finally:
                    self.assertTrue(remove_job(job["id"]))
                self.assertIsNone(get_job(job["id"]))

        suite = (unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:], ProviderRegression)
                 if len(sys.argv) > 1 else unittest.defaultTestLoader.loadTestsFromTestCase(ProviderRegression))
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
        import logging
        logging.shutdown()
        if not outcome.wasSuccessful():
            sys.exit(1)
