import os
import importlib
import inspect
from typing import Dict, List, Type, Any
from telethon import events, TelegramClient
import logging

logger = logging.getLogger(__name__)

class Plugin:
    """Base class for all plugins."""
    def __init__(self, client: TelegramClient):
        self.client = client
        self.name = self.__class__.__name__

    async def init(self):
        """Initialize the plugin. Override this method to add startup logic."""
        pass

class PluginLoader:
    def __init__(self, plugins_folder: str = "plugins"):
        self.plugins_folder = plugins_folder
        self.loaded_plugins: Dict[str, Type[Plugin]] = {}
        self.active_instances: Dict[int, Dict[str, Plugin]] = {}

    async def discover_plugins(self) -> List[Type[Plugin]]:
        """Discover and load all plugins from the plugins directory."""
        plugins: List[Type[Plugin]] = []
        
        if not os.path.exists(self.plugins_folder):
            os.makedirs(self.plugins_folder)
            return plugins

        for filename in os.listdir(self.plugins_folder):
            if filename.endswith('.py') and not filename.startswith('_'):
                try:
                    module_path = f"{self.plugins_folder}.{filename[:-3]}"
                    module = importlib.import_module(module_path)
                    
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and issubclass(obj, Plugin)
                            and obj != Plugin):
                            self.loaded_plugins[obj.__name__] = obj
                            plugins.append(obj)
                            
                except Exception as e:
                    logger.error(f"Error loading plugin {filename}: {e}")
                    continue

        return plugins

    async def init_plugins(self, client: TelegramClient, user_id: int):
        """Initialize plugins for a specific user's client."""
        if user_id not in self.active_instances:
            self.active_instances[user_id] = {}

        for plugin_name, plugin_class in self.loaded_plugins.items():
            try:
                plugin = plugin_class(client)
                await plugin.init()
                self.active_instances[user_id][plugin_name] = plugin
                logger.info(f"Initialized plugin {plugin_name} for user {user_id}")
            except Exception as e:
                logger.error(f"Error initializing plugin {plugin_name} for user {user_id}: {e}")

    def get_active_plugins(self, user_id: int) -> Dict[str, Plugin]:
        """Get all active plugin instances for a user."""
        return self.active_instances.get(user_id, {})

    async def reload_plugin(self, plugin_name: str, user_id: int, client: TelegramClient) -> bool:
        """Reload a specific plugin for a user."""
        try:
            if user_id in self.active_instances:
                self.active_instances[user_id].pop(plugin_name, None)

            module_path = f"{self.plugins_folder}.{plugin_name.lower()}"
            module = importlib.reload(importlib.import_module(module_path))

            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and issubclass(obj, Plugin)
                    and obj != Plugin and obj.__name__ == plugin_name):
                    self.loaded_plugins[plugin_name] = obj
                    
                    plugin = obj(client)
                    await plugin.init()
                    
                    if user_id not in self.active_instances:
                        self.active_instances[user_id] = {}
                    self.active_instances[user_id][plugin_name] = plugin
                    
                    return True

        except Exception as e:
            logger.error(f"Error reloading plugin {plugin_name}: {e}")
        
        return False

    async def unload_plugins(self, user_id: int):
        """Unload all plugins for a specific user."""
        if user_id in self.active_instances:
            del self.active_instances[user_id]
