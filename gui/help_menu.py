from config.app_config import singleton_settings
from utils.paths import get_main_dir
import generictools.personalized_widgets as pwi

app_settings = singleton_settings()


def show_file_paths(parent_window):
    main_dir = get_main_dir()
    coil_table_file = main_dir.joinpath(app_settings.get_value("vc_table_file")).absolute()
    startup_state_file = main_dir.joinpath(app_settings.get_value("startup_state_file")).absolute()

    result_text = (f"#### Installation folder<br></br>{main_dir}"
                   "<br></br>  \n"
                   f"#### Coil wire definitions file<br></br>{coil_table_file}"
                   "<br></br>  \n"
                   f"#### Start-up state file<br></br>{startup_state_file}"
                   )

    popup = pwi.ResultTextBox("File paths",
                              result_text,
                              monospace=False,
                              parent=parent_window,
                              markdown=True,
                              )

    popup.exec()
