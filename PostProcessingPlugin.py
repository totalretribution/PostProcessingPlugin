# Copyright (c) 2015 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the AGPLv3 or higher.
from PyQt5.QtCore import  QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt5.QtQuick import QQuickView
from PyQt5.QtQml import QQmlComponent, QQmlContext

from UM.PluginRegistry import PluginRegistry
from UM.Application import Application
from UM.Preferences import Preferences
from UM.Extension import Extension
from UM.Logger import Logger

from pydoc import locate

import os.path
import pkgutil
import sys

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("PostProcessingPlugin")

class PostProcessingPlugin(QObject,  Extension):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.addMenuItem(i18n_catalog.i18n("Modify G-Code"), self.showPopup)
        self._view = None
        
        # Loaded scripts are all scripts that can be used
        self._loaded_scripts = {} 
        self._script_labels = {}
        
        # Script list contains instances of scripts in loaded_scripts. There can be duplicates and they will be executed in sequence.
        self._script_list = [] 
        self._selected_script_index = 0
        
    @pyqtSlot(int, result = "QVariant")
    def getSettingModel(self, index):
        return self._script_list[index].getSettingsModel()
    
    @pyqtSlot(str, "QVariant")
    ## Called when the setting is changed.
    def setSettingValue(self, key, value):
        setting = self._script_list[self._selected_script_index].getSettings().getSettingByKey(key)
        if setting:
            setting.setValue(value)
        #self._script_list[self._selected_script_index].getSettings().setSettingValue
    
    selectedIndexChanged = pyqtSignal()
    @pyqtProperty("QVariant", notify = selectedIndexChanged)
    def selectedScriptSettingsModel(self):
        try:
            return self._script_list[self._selected_script_index].getSettingsModel()
        except:
            return None
    
    @pyqtSlot()
    def execute(self):
        scene = Application.getInstance().getController().getScene()
        if hasattr(scene, "gcode_list"):
            gcode_list = getattr(scene, "gcode_list")
            if gcode_list:
                for script in self._script_list:
                    try:
                        gcode_list = script.execute(gcode_list)
                    except Exception as e:
                        print(e)
                        pass
                setattr(scene, "gcode_list", gcode_list)

    @pyqtSlot(int)
    def setSelectedScriptIndex(self, index):
        self._selected_script_index = index
        self.selectedIndexChanged.emit()
    
    @pyqtProperty(int, notify = selectedIndexChanged)
    def selectedScriptIndex(self):
        return self._selected_script_index
    
    @pyqtSlot(int, int)
    def moveScript(self, index, new_index):
        if new_index < 0 or new_index > len(self._script_list)-1:
            return #nothing needs to be done
        else:
            # Magical switch code.
            self._script_list[new_index], self._script_list[index] = self._script_list[index], self._script_list[new_index]
            self.scriptListChanged.emit()
            self.selectedIndexChanged.emit() #Ensure that settings are updated
    
    ##  Remove a script from the active script list by index.
    @pyqtSlot(int)
    def removeScriptByIndex(self, index):
        self._script_list.pop(index)
        if len(self._script_list) - 1 < self._selected_script_index:
            self._selected_script_index = len(self._script_list) - 1
        self.scriptListChanged.emit()
        self.selectedIndexChanged.emit() #Ensure that settings are updated
    
    ##  Load all scripts from provided path. This should probably only be done on init.
    def loadAllScripts(self, path):
        scripts = pkgutil.iter_modules(path = [path])
        for loader, script_name, ispkg in scripts: 
            if script_name not in sys.modules:
                # Import module
                loaded_script = __import__("PostProcessingPlugin.scripts."+ script_name, fromlist = [script_name])
                loaded_class = getattr(loaded_script, script_name)
                temp_object = loaded_class()
                try: 
                    setting_data = temp_object.getSettingData()
                    if "label" in setting_data and "key" in setting_data:
                        self._script_labels[setting_data["key"]] = setting_data["label"]
                        self._loaded_scripts[setting_data["key"]] = loaded_class
                    else:
                        Logger.log("w", "Script %s.py has no label or key", script_name)
                        self._script_labels[script_name] = script_name
                        self._loaded_scripts[script_name] = loaded_class
                    #self._script_list.append(loaded_class())
                    self.loadedScriptListChanged.emit()
                except AttributeError:
                    Logger.log("e", "Script %s.py is not a recognised script type. Ensure it inherits Script", script_name)
                except NotImplementedError:
                    Logger.log("e", "Script %s.py has no implemented settings",script_name)

    loadedScriptListChanged = pyqtSignal()
    @pyqtProperty("QVariantList", notify = loadedScriptListChanged)
    def loadedScriptList(self):
        return list(self._loaded_scripts.keys())
    
    @pyqtSlot(str, result = str)
    def getScriptLabelByKey(self, key):
        return self._script_labels[key]
    
    scriptListChanged = pyqtSignal()
    @pyqtProperty("QVariantList", notify = scriptListChanged)
    def scriptList(self):
        script_list = [script.getSettingData()["key"] for script in self._script_list]
        return script_list
    
    @pyqtSlot(str)
    def addScriptToList(self, key):
        self._script_list.append(self._loaded_scripts[key]())
        self.setSelectedScriptIndex(len(self._script_list) - 1)
        self.scriptListChanged.emit()
    
    ##  Creates the view used by show popup. The view is saved because of the fairly aggressive garbage collection.
    def _createView(self):
        ## Load all scripts in the scripts folder
        self.loadAllScripts(os.path.join(PluginRegistry.getInstance().getPluginPath("PostProcessingPlugin"), "scripts"))
        
        path = QUrl.fromLocalFile(os.path.join(PluginRegistry.getInstance().getPluginPath("PostProcessingPlugin"), "PostProcessingPlugin.qml"))
        self._component = QQmlComponent(Application.getInstance()._engine, path)

        self._context = QQmlContext(Application.getInstance()._engine.rootContext())
        self._context.setContextProperty("manager", self)
        self._view = self._component.create(self._context)
    
    ##  Show the (GUI) popup of the post processing plugin.
    def showPopup(self):
        if self._view is None:
            self._createView()
        self._view.show()