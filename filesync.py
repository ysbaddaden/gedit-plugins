import re, os, shutil
from gettext import gettext as _
import gtk, gedit

config_paths = {
  "/home/julien/work/ligos/pointscommuns/": [
    "/home/www/pcom/",
  ],
}

# excludes any .* directories and files
config_exclude_patterns = [
  # directories
#  ".*/\.svn/",
#  ".*/\.git/",
  ".*/\.",
  
  # files
  ".*/(AUTHORS|README|LICENSE)",
  ".*/\..*/",
  ".*\.bak",
  ".*\.doxyfile",
  ".*/*~",
#  ".*/__*",
]

# Menu item
ui_str = """<ui>
  <menubar name="MenuBar">
    <menu name="ToolsMenu" action="Tools">
      <placeholder name="Refresh File Sync">
        <menuitem name="FileSyncRefresh" action="FileSyncRefresh"/>
        <menuitem name="FileSyncForce" action="FileSyncForce"/>
      </placeholder>
    </menu>
  </menubar>
</ui>
"""

# TODO: Use GVFS to tramsparently sync from and to remote servers.
# TODO: Remove messages from statusbar after some time.
class FileSyncWindowHelper:
  def __init__(self, plugin, window):
    self._window = window
    self._plugin = plugin
    
    self._statusbar = window.get_statusbar()
    self._insert_menu()
    
    for document in self._window.get_documents():
      self.connect_handlers(document)
    
    tab_added_id = self._window.connect("tab_added", lambda window, tab: self.connect_handlers(tab.get_document()))
    window.set_data("FileSyncPluginHandlerId", tab_added_id)
  
  def deactivate(self):
    self._remove_menu()
    
    for document in self._window.get_documents():
      self.disconnect_handlers(document)
    
    tab_added_id = self._window.get_data("FileSyncPluginHandlerId")
    self._window.disconnect(tab_added_id)
    self._window.set_data("FileSyncPluginHandlerId", None)
    
    for document in self._window.get_documents():
      self.disconnect_handlers(document)
    
    self._window = None
    self._plugin = None
    self._action_group = None
  
  def update_ui(self):
    self._action_group.set_sensitive(self._window.get_active_document != None)
  
  
  # Displays a message in window's status bar.
  def _announce(self, message):
#    print "filesync.plugin: " + message
    context_id = self._statusbar.get_context_id("FileSyncPluginStatusBar")
    self._statusbar.push(context_id, message)
  
  
  # Adds the menu items.
  def _insert_menu(self):
    manager = self._window.get_ui_manager()
    
    self._action_group = gtk.ActionGroup("FileSyncPluginActions")
    self._action_group.add_actions([("FileSyncRefresh", None, _("Refresh File Sync"),
      None, _("Refreshes file synchronisation"), self.on_force_refresh)])
    self._action_group.add_actions([("FileSyncForce", None, _("Force File Sync"),
      None, _("Forces file synchronisation"), self.on_force_sync)])
    
    manager.insert_action_group(self._action_group, -1)
    self._ui_id = manager.add_ui_from_string(ui_str)
  
  # Removes the menu items.
  def _remove_menu(self):
    manager = self._window.get_ui_manager()
    manager.remove_ui(self._ui_id)
    manager.remove_action_group(self._action_group)
    manager.ensure_update()
  
  
  # Connects events handlers.
  def connect_handlers(self, document):
    saved_id = document.connect("saved", self.on_file_saved, document)
    document.set_data("FileSyncSavedId", saved_id)
  
  # Disconnects events handlers.
  def disconnect_handlers(self, document):
    saved_id = document.get_data("FileSyncSavedId")
    if saved_id:
      document.disconnect(saved_id)
      document.set_data("FileSyncSavedId", None)
  
  # Event: when file is saved, sync it!
  def on_file_saved(self, document, a, b):
    uri = document.get_uri()
    path_from = re.sub('file://', '', uri)
    
    # uri matches an exclude pattern?
    if self._is_excluded_path(path_from):
      return;
    
    # in a path to sync?
    for path in config_paths:
      if not re.match(path, path_from):
        continue
      
      if not os.path.exists(path_from):
        return
      
      for base_path_to in config_paths[path]:
        path_to = re.sub(path, base_path_to, path_from)
        self._do_sync_file(path_from, path_to)
  
      self._announce("Synced saved file: " + path_from)
      
  # Menu item callback: refreshes unsynced files.
  def on_force_refresh(self, action):
    self._sync_files(True)
  
  # Menu item callback: forces file sync
  def on_force_sync(self, action):
    self._sync_files(True)
  
  
  # Syncs files.
  def _sync_files(self, force_sync=False):
    document = self._window.get_active_document()
    path = re.sub('file://', '', document.get_uri())
    
    # in a path to sync?
    for src_path in config_paths:
      if not re.match(src_path, path):
        continue
      
      if force_sync:
        self._announce(_("Syncing: %s ...") % src_path)
      else:
        self._announce(_("Refreshing: %s ...") % src_path)
      
      for root, dirs, files in os.walk(src_path):
        if self._is_excluded_path(root):
            continue
        
        for filename in files:
          if self._is_excluded_path(os.path.join(root, filename)):
            continue
          
          for dest_path in config_paths[src_path]:
            path_from = os.path.join(root, filename)
            path_to   = re.sub(src_path, dest_path, path_from)
            
            if force_sync:
              self._do_sync_file(path_from, path_to)
            else:
              self._sync_file_if_newer(path_from, path_to)
      
      if force_sync:
        self._announce(_("Synced: %s") % src_path)
      else:
        self._announce(_("Refreshed: %s") % src_path)
  
  def _is_excluded_path(self, path):
    for pattern in config_exclude_patterns:
      if re.match(pattern, path):
        return True
    return False
  
  def _sync_file_if_newer(self, path_from, path_to):
    if not os.path.exists(path_to) or os.path.getmtime(path_from) > os.path.getmtime(path_to):
      self._do_sync_file(path_from, path_to)
  
  def _do_sync_file(self, path_from, path_to):
    path_to_dir = os.path.dirname(path_to)
    
    # creates parent directories
    if not os.path.exists(path_to_dir):
      os.makedirs(path_to_dir);
      shutil.copymode(os.path.dirname(path_from), path_to_dir)
#      print "mkdir -p " + path_to_dir
    
    # syncs
    if os.path.isfile(path_from):
      shutil.copyfile(path_from, path_to)
      shutil.copymode(path_from, path_to)
#      print "cp " + path_from + " " + path_to
    elif os.path.isdir(path_from):
      pass


class FileSyncPlugin(gedit.Plugin):
  def __init__(self):
    gedit.Plugin.__init__(self)
    self._instances = {}

  def activate(self, window):
   self._instances[window] = FileSyncWindowHelper(self, window)

  def deactivate(self, window):
    self._instances[window].deactivate()
    del self._instances[window]

  def update_ui(self, window):
    self._instances[window].update_ui()
  
