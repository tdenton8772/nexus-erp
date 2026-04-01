defmodule NexusUiWeb.MappingEditorLive do
  @moduledoc """
  Interactive field mapping editor for a pipeline.

  Shows source schema fields on the left and target schema fields on the right.
  Users can:
    - Manually map fields by selecting source + target + transform
    - Request the agent to propose mappings automatically
    - Review and approve/reject agent proposals inline
    - Edit transform expressions for computed fields
  """
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(%{"id" => pipeline_id}, _session, socket) do
    pipeline = load_pipeline(pipeline_id)
    source_schema = load_schema(pipeline["source_connector_id"], pipeline["entity_name"])
    target_schema = load_schema(pipeline["target_connector_id"], pipeline["entity_name"])
    mappings = load_mappings(pipeline_id)

    {:ok,
     socket
     |> assign(:page_title, "Mapping Editor — #{pipeline["name"]}")
     |> assign(:pipeline, pipeline)
     |> assign(:pipeline_id, pipeline_id)
     |> assign(:source_schema, source_schema)
     |> assign(:target_schema, target_schema)
     |> assign(:mappings, mappings)
     |> assign(:selected_source, nil)
     |> assign(:selected_target, nil)
     |> assign(:selected_transform, "passthrough")
     |> assign(:expression, "")
     |> assign(:agent_running, false)
     |> assign(:pending_proposal, nil)}
  end

  @impl true
  def handle_event("select_source_field", %{"field" => field}, socket) do
    {:noreply, assign(socket, :selected_source, field)}
  end

  def handle_event("select_target_field", %{"field" => field}, socket) do
    {:noreply, assign(socket, :selected_target, field)}
  end

  def handle_event("set_transform", %{"transform" => t}, socket) do
    {:noreply, assign(socket, :selected_transform, t)}
  end

  def handle_event("set_expression", %{"value" => expr}, socket) do
    {:noreply, assign(socket, :expression, expr)}
  end

  def handle_event("add_mapping", _, socket) do
    params = %{
      source_field: socket.assigns.selected_source,
      target_field: socket.assigns.selected_target,
      transform_name: socket.assigns.selected_transform,
      expression: socket.assigns.expression
    }

    case ApiClient.upsert_mapping(socket.assigns.pipeline_id, params) do
      {:ok, _} ->
        {:noreply,
         socket
         |> assign(:selected_source, nil)
         |> assign(:selected_target, nil)
         |> assign(:selected_transform, "passthrough")
         |> assign(:expression, "")
         |> reload_mappings()}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, "Failed to save mapping: #{inspect(err.body)}")}
    end
  end

  def handle_event("delete_mapping", %{"id" => id}, socket) do
    case ApiClient.delete_mapping(socket.assigns.pipeline_id, id) do
      {:ok, _} -> {:noreply, reload_mappings(socket)}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("request_agent_mapping", _, socket) do
    case ApiClient.trigger_schema_mapping(socket.assigns.pipeline_id) do
      {:ok, run} ->
        {:noreply,
         socket
         |> assign(:agent_running, true)
         |> assign(:agent_run_id, run["run_id"])
         |> put_flash(:info, "Agent is generating mappings...")}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, "Agent failed to start: #{inspect(err.body)}")}
    end
  end

  def handle_event("approve_proposal", %{"id" => proposal_id}, socket) do
    case ApiClient.review_proposal(proposal_id, "approve") do
      {:ok, _} ->
        {:noreply,
         socket
         |> assign(:pending_proposal, nil)
         |> reload_mappings()
         |> put_flash(:info, "Proposal approved and mappings applied")}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("reject_proposal", %{"id" => proposal_id}, socket) do
    case ApiClient.review_proposal(proposal_id, "reject") do
      {:ok, _} ->
        {:noreply,
         socket
         |> assign(:pending_proposal, nil)
         |> put_flash(:info, "Proposal rejected")}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  defp load_pipeline(id) do
    case ApiClient.get_pipeline(id) do
      {:ok, p} -> p
      _ -> %{}
    end
  end

  defp load_schema(connector_id, entity) when is_binary(connector_id) and is_binary(entity) do
    case ApiClient.get_schema(connector_id, entity) do
      {:ok, schema} -> schema
      _ -> %{"fields" => []}
    end
  end

  defp load_schema(_, _), do: %{"fields" => []}

  defp load_mappings(pipeline_id) do
    case ApiClient.list_mappings(pipeline_id) do
      {:ok, data} -> data["items"] || data
      _ -> []
    end
  end

  defp reload_mappings(socket) do
    assign(socket, :mappings, load_mappings(socket.assigns.pipeline_id))
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Mapping Editor</h1>
          <p class="text-gray-500 text-sm mt-1">
            <%= @pipeline["name"] %> — <%= @pipeline["entity_name"] %>
          </p>
        </div>
        <div class="flex gap-2">
          <button phx-click="request_agent_mapping"
                  disabled={@agent_running}
                  class="btn-secondary flex items-center gap-1">
            <%= if @agent_running do %>
              <span class="animate-spin">⟳</span> Agent working...
            <% else %>
              ✦ Agent Auto-Map
            <% end %>
          </button>
          <.link navigate={"/pipelines/#{@pipeline_id}/transformation"} class="btn-primary">
            View Transformation Code →
          </.link>
        </div>
      </div>

      <%!-- Pending agent proposal banner --%>
      <%= if @pending_proposal do %>
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p class="font-medium text-blue-800">Agent proposal ready for review</p>
          <p class="text-sm text-blue-600 mt-1">
            Confidence: <%= @pending_proposal["confidence_scores"]["overall"] %>
          </p>
          <div class="flex gap-2 mt-3">
            <button phx-click="approve_proposal"
                    phx-value-id={@pending_proposal["id"]}
                    class="btn-primary text-sm">
              Approve & Apply
            </button>
            <button phx-click="reject_proposal"
                    phx-value-id={@pending_proposal["id"]}
                    class="btn-secondary text-sm">
              Reject
            </button>
          </div>
        </div>
      <% end %>

      <%!-- Three-column editor --%>
      <div class="grid grid-cols-3 gap-4">
        <%!-- Source fields --%>
        <div class="bg-white rounded-lg shadow">
          <div class="px-4 py-3 border-b bg-gray-50">
            <h3 class="font-semibold text-gray-700 text-sm">
              Source: <%= @pipeline["source_system"] %>
            </h3>
          </div>
          <div class="p-2 space-y-1 max-h-96 overflow-y-auto">
            <%= for field <- @source_schema["fields"] || [] do %>
              <button
                phx-click="select_source_field"
                phx-value-field={field["name"]}
                class={"w-full text-left px-3 py-2 rounded text-sm hover:bg-blue-50 transition " <>
                  if @selected_source == field["name"], do: "bg-blue-100 ring-1 ring-blue-400", else: ""}>
                <span class="font-mono"><%= field["name"] %></span>
                <span class="text-gray-400 text-xs ml-2"><%= field["data_type"] %></span>
              </button>
            <% end %>
          </div>
        </div>

        <%!-- Mapping configuration --%>
        <div class="bg-white rounded-lg shadow">
          <div class="px-4 py-3 border-b bg-gray-50">
            <h3 class="font-semibold text-gray-700 text-sm">Add Mapping</h3>
          </div>
          <div class="p-4 space-y-3">
            <div>
              <label class="text-xs text-gray-500">Source Field</label>
              <p class={"px-3 py-2 rounded border text-sm " <>
                        if @selected_source, do: "bg-blue-50 border-blue-300", else: "bg-gray-50 border-gray-200 text-gray-400"}>
                <%= @selected_source || "← Select from left" %>
              </p>
            </div>
            <div>
              <label class="text-xs text-gray-500">Transform</label>
              <select phx-change="set_transform" name="transform"
                      class="w-full rounded border border-gray-300 px-3 py-2 text-sm">
                <option value="passthrough">passthrough</option>
                <option value="str">str (cast to string)</option>
                <option value="int">int (cast to integer)</option>
                <option value="decimal_to_float">decimal → float</option>
                <option value="float_to_decimal">float → decimal</option>
                <option value="intacct_date_to_iso8601">Intacct date → ISO 8601</option>
                <option value="upper">upper case</option>
                <option value="lower">lower case</option>
                <option value="compute">compute (custom expression)</option>
              </select>
            </div>
            <%= if @selected_transform == "compute" do %>
              <div>
                <label class="text-xs text-gray-500">Expression (Python)</label>
                <textarea
                  phx-blur="set_expression"
                  phx-value-value={@expression}
                  name="expression"
                  rows="4"
                  class="w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono"
                  placeholder="if record.get('STATUS') == 'A':\n    return 'Active'\nreturn 'Inactive'"
                ><%= @expression %></textarea>
              </div>
            <% end %>
            <div>
              <label class="text-xs text-gray-500">Target Field</label>
              <p class={"px-3 py-2 rounded border text-sm " <>
                        if @selected_target, do: "bg-green-50 border-green-300", else: "bg-gray-50 border-gray-200 text-gray-400"}>
                <%= @selected_target || "Select from right →" %>
              </p>
            </div>
            <button
              phx-click="add_mapping"
              disabled={is_nil(@selected_source) or is_nil(@selected_target)}
              class="w-full btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed">
              Add Mapping
            </button>
          </div>
        </div>

        <%!-- Target fields --%>
        <div class="bg-white rounded-lg shadow">
          <div class="px-4 py-3 border-b bg-gray-50">
            <h3 class="font-semibold text-gray-700 text-sm">
              Target: <%= @pipeline["target_system"] %>
            </h3>
          </div>
          <div class="p-2 space-y-1 max-h-96 overflow-y-auto">
            <%= for field <- @target_schema["fields"] || [] do %>
              <button
                phx-click="select_target_field"
                phx-value-field={field["name"]}
                class={"w-full text-left px-3 py-2 rounded text-sm hover:bg-green-50 transition " <>
                  if @selected_target == field["name"], do: "bg-green-100 ring-1 ring-green-400", else: ""}>
                <span class="font-mono"><%= field["name"] %></span>
                <span class="text-gray-400 text-xs ml-2"><%= field["data_type"] %></span>
              </button>
            <% end %>
          </div>
        </div>
      </div>

      <%!-- Current mappings table --%>
      <div class="bg-white rounded-lg shadow">
        <div class="px-4 py-3 border-b">
          <h2 class="font-semibold text-gray-700">Current Mappings (<%= length(@mappings) %>)</h2>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-4 py-2 text-left">Source Field</th>
              <th class="px-4 py-2 text-left">Transform</th>
              <th class="px-4 py-2 text-left">Target Field</th>
              <th class="px-4 py-2 text-left">Expression</th>
              <th class="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for m <- @mappings do %>
              <tr class="hover:bg-gray-50">
                <td class="px-4 py-2 font-mono text-blue-700"><%= m["source_field"] || "—" %></td>
                <td class="px-4 py-2">
                  <span class="bg-gray-100 px-2 py-0.5 rounded text-xs font-mono">
                    <%= m["transform_name"] %>
                  </span>
                </td>
                <td class="px-4 py-2 font-mono text-green-700"><%= m["target_field"] || "—" %></td>
                <td class="px-4 py-2 font-mono text-gray-500 text-xs truncate max-w-xs">
                  <%= m["expression"] %>
                </td>
                <td class="px-4 py-2 text-right">
                  <button phx-click="delete_mapping" phx-value-id={m["id"]}
                          class="text-red-400 hover:text-red-600 text-xs">✕</button>
                </td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>
    </div>
    """
  end
end
