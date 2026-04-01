defmodule NexusUiWeb.ErrorHTML do
  use NexusUiWeb, :html

  # Renders a plain HTML error page for any status code.
  # To customise, create templates in lib/nexus_ui_web/controllers/error_html/
  # e.g. error_html/404.html.heex

  def render(template, _assigns) do
    Phoenix.Controller.status_message_from_template(template)
  end
end
