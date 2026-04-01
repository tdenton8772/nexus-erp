defmodule NexusUiWeb.PipelinesLive do
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page_title, "Pipelines")
     |> assign(:show_modal, false)
     |> assign(:form_errors, %{})
     |> assign(:connectors, [])
     |> load_pipelines()}
  end

  @impl true
  def handle_params(params, _url, socket) do
    {:noreply, apply_action(socket, socket.assigns.live_action, params)}
  end

  defp apply_action(socket, :index, _params), do: socket

  defp apply_action(socket, :new, _params) do
    connectors =
      case ApiClient.list_connectors() do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    socket
    |> assign(:show_modal, true)
    |> assign(:connectors, connectors)
    |> assign(:form, %{
      "name" => "",
      "entity_name" => "",
      "source_connector_id" => "",
      "target_connector_id" => "",
      "direction" => "bidirectional",
      "poll_interval_seconds" => "300"
    })
  end

  @impl true
  def handle_event("close_modal", _, socket) do
    {:noreply, push_patch(socket, to: "/pipelines")}
  end

  def handle_event("save_pipeline", %{"pipeline" => params}, socket) do
    case ApiClient.create_pipeline(params) do
      {:ok, pipeline} ->
        {:noreply,
         socket
         |> put_flash(:info, "Pipeline created")
         |> push_navigate(to: "/pipelines/#{pipeline["id"]}")}

      {:error, err} ->
        errors = (err.body["detail"] || []) |> format_errors()
        {:noreply, assign(socket, :form_errors, errors)}
    end
  end

  def handle_event("start_pipeline", %{"id" => id}, socket) do
    case ApiClient.start_pipeline(id) do
      {:ok, _} -> {:noreply, socket |> put_flash(:info, "Pipeline started") |> load_pipelines()}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("pause_pipeline", %{"id" => id}, socket) do
    case ApiClient.pause_pipeline(id) do
      {:ok, _} -> {:noreply, socket |> put_flash(:info, "Pipeline paused") |> load_pipelines()}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("delete_pipeline", %{"id" => id}, socket) do
    case ApiClient.delete_pipeline(id) do
      {:ok, _} -> {:noreply, socket |> put_flash(:info, "Pipeline deleted") |> load_pipelines()}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  defp load_pipelines(socket) do
    pipelines =
      case ApiClient.list_pipelines() do
        {:ok, data} -> data["items"] || data
        _ -> []
      end

    assign(socket, :pipelines, pipelines)
  end

  defp format_errors(details) when is_list(details) do
    Enum.reduce(details, %{}, fn %{"loc" => loc, "msg" => msg}, acc ->
      field = List.last(loc)
      Map.put(acc, field, msg)
    end)
  end

  defp format_errors(_), do: %{}

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6">
      <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold text-gray-900">Pipelines</h1>
        <.link patch="/pipelines/new" class="btn-primary">+ New Pipeline</.link>
      </div>

      <div class="bg-white rounded-lg shadow overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-6 py-3 text-left">Name</th>
              <th class="px-6 py-3 text-left">Entity</th>
              <th class="px-6 py-3 text-left">Direction</th>
              <th class="px-6 py-3 text-left">Status</th>
              <th class="px-6 py-3 text-left">Last Sync</th>
              <th class="px-6 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for p <- @pipelines do %>
              <tr class="hover:bg-gray-50">
                <td class="px-6 py-4 font-medium">
                  <.link navigate={"/pipelines/#{p["id"]}"} class="text-blue-600 hover:underline">
                    <%= p["name"] %>
                  </.link>
                </td>
                <td class="px-6 py-4 text-gray-600"><%= p["entity_name"] %></td>
                <td class="px-6 py-4 text-gray-600 capitalize">
                  <%= String.replace(p["direction"] || "bidirectional", "_", " ") %>
                </td>
                <td class="px-6 py-4">
                  <span class={"px-2 py-1 rounded text-xs font-medium " <> status_class(p["status"])}>
                    <%= p["status"] %>
                  </span>
                </td>
                <td class="px-6 py-4 text-gray-500 text-xs"><%= p["last_sync_at"] || "—" %></td>
                <td class="px-6 py-4 text-right space-x-3">
                  <%= if p["status"] == "active" do %>
                    <button phx-click="pause_pipeline" phx-value-id={p["id"]}
                            class="text-yellow-600 hover:underline text-xs">Pause</button>
                  <% else %>
                    <button phx-click="start_pipeline" phx-value-id={p["id"]}
                            class="text-green-600 hover:underline text-xs">Start</button>
                  <% end %>
                  <.link navigate={"/pipelines/#{p["id"]}/mappings"}
                         class="text-blue-600 hover:underline text-xs">Mappings</.link>
                  <button phx-click="delete_pipeline" phx-value-id={p["id"]}
                          data-confirm="Delete this pipeline?"
                          class="text-red-500 hover:underline text-xs">Delete</button>
                </td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>

      <%!-- New Pipeline Modal --%>
      <%= if @show_modal do %>
        <.modal>
          <h2 class="text-lg font-bold mb-4">New Pipeline</h2>
          <form phx-submit="save_pipeline" class="space-y-4">
            <.field label="Name" name="pipeline[name]" value={@form["name"]}
                    error={@form_errors["name"]} />
            <.field label="Entity Name" name="pipeline[entity_name]" value={@form["entity_name"]}
                    placeholder="Invoice, Vendor, Customer..."
                    error={@form_errors["entity_name"]} />
            <.select_field label="Source Connector" name="pipeline[source_connector_id]"
                           options={connector_options(@connectors)}
                           error={@form_errors["source_connector_id"]} />
            <.select_field label="Target Connector" name="pipeline[target_connector_id]"
                           options={connector_options(@connectors)}
                           error={@form_errors["target_connector_id"]} />
            <.select_field label="Direction" name="pipeline[direction]"
                           options={[
                             {"Bidirectional", "bidirectional"},
                             {"Source → Target only", "source_to_target"},
                             {"Target → Source only", "target_to_source"}
                           ]} />
            <.field label="Poll Interval (seconds)" name="pipeline[poll_interval_seconds]"
                    value={@form["poll_interval_seconds"]} type="number" />
            <div class="flex justify-end gap-2 pt-2">
              <button type="button" phx-click="close_modal" class="btn-secondary">Cancel</button>
              <button type="submit" class="btn-primary">Create Pipeline</button>
            </div>
          </form>
        </.modal>
      <% end %>
    </div>
    """
  end

  defp status_class("active"), do: "bg-green-100 text-green-800"
  defp status_class("error"), do: "bg-red-100 text-red-800"
  defp status_class("paused"), do: "bg-yellow-100 text-yellow-800"
  defp status_class(_), do: "bg-gray-100 text-gray-800"

  defp connector_options(connectors) do
    Enum.map(connectors, &{&1["display_name"], &1["id"]})
  end
end
