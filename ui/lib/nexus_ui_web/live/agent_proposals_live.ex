defmodule NexusUiWeb.AgentProposalsLive do
  @moduledoc """
  Lists all pending agent proposals (schema mappings, healing actions).
  Users approve, reject, or provide feedback to iterate on proposals.
  """
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      Phoenix.PubSub.subscribe(NexusUi.PubSub, "agent:proposals")
    end

    {:ok,
     socket
     |> assign(:page_title, "Agent Proposals")
     |> assign(:filter_status, "pending_review")
     |> assign(:feedback_map, %{})
     |> load_proposals()}
  end

  @impl true
  def handle_info({:new_proposal, _proposal}, socket) do
    {:noreply, load_proposals(socket)}
  end

  @impl true
  def handle_event("set_filter", %{"value" => val}, socket) do
    {:noreply, socket |> assign(:filter_status, val) |> load_proposals()}
  end

  def handle_event("set_feedback", %{"id" => id, "value" => feedback}, socket) do
    {:noreply, assign(socket, :feedback_map, Map.put(socket.assigns.feedback_map, id, feedback))}
  end

  def handle_event("approve", %{"id" => id}, socket) do
    case ApiClient.review_proposal(id, "approve") do
      {:ok, _} ->
        {:noreply, socket |> put_flash(:info, "Proposal approved") |> load_proposals()}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("reject", %{"id" => id}, socket) do
    case ApiClient.review_proposal(id, "reject") do
      {:ok, _} ->
        {:noreply, socket |> put_flash(:info, "Proposal rejected") |> load_proposals()}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("modify", %{"id" => id}, socket) do
    feedback = Map.get(socket.assigns.feedback_map, id, "")

    case ApiClient.review_proposal(id, "modify", feedback) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Feedback sent. Agent will revise the proposal.")
         |> assign(:feedback_map, Map.delete(socket.assigns.feedback_map, id))
         |> load_proposals()}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  defp load_proposals(socket) do
    params = if socket.assigns.filter_status == "all", do: %{}, else: %{status: socket.assigns.filter_status}

    proposals =
      case ApiClient.list_proposals(params) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    assign(socket, :proposals, proposals)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-4">
      <div class="flex justify-between items-center">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Agent Proposals</h1>
          <p class="text-sm text-gray-500 mt-1">
            Review schema mappings and healing actions proposed by the agent.
          </p>
        </div>
        <select phx-change="set_filter" name="filter"
                class="rounded border border-gray-300 px-3 py-1.5 text-sm">
          <option value="pending_review">Pending Review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      <%= if @proposals == [] do %>
        <div class="text-center py-16 text-gray-400">
          <p class="text-4xl mb-3">✦</p>
          <p class="font-medium">No proposals</p>
          <p class="text-sm mt-1">
            Run schema discovery or trigger a pipeline to generate agent proposals.
          </p>
        </div>
      <% end %>

      <%= for proposal <- @proposals do %>
        <div class="bg-white rounded-lg shadow overflow-hidden">
          <div class="px-4 py-3 border-b flex justify-between items-center bg-gray-50">
            <div>
              <span class={"px-2 py-0.5 rounded text-xs font-medium " <> proposal_type_class(proposal["trigger_type"])}>
                <%= proposal["trigger_type"] %>
              </span>
              <span class="ml-2 text-sm text-gray-600">
                Pipeline: <%= proposal["pipeline_id"] %>
              </span>
            </div>
            <span class="text-xs text-gray-400"><%= proposal["created_at"] %></span>
          </div>

          <%!-- Proposed mappings table --%>
          <div class="p-4">
            <h3 class="text-sm font-medium text-gray-700 mb-2">
              Proposed Mappings (<%= length(proposal["proposal_json"]["field_mappings"] || []) %>)
            </h3>
            <table class="w-full text-xs">
              <thead class="text-gray-500 uppercase border-b">
                <tr>
                  <th class="py-1 text-left">Source Field</th>
                  <th class="py-1 text-left">Transform</th>
                  <th class="py-1 text-left">Target Field</th>
                  <th class="py-1 text-left">Confidence</th>
                  <th class="py-1 text-left">Note</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50">
                <%= for m <- proposal["proposal_json"]["field_mappings"] || [] do %>
                  <tr>
                    <td class="py-1.5 font-mono text-blue-700"><%= m["source_field"] %></td>
                    <td class="py-1.5">
                      <span class="bg-gray-100 px-1.5 rounded font-mono"><%= m["transform"] %></span>
                    </td>
                    <td class="py-1.5 font-mono text-green-700"><%= m["target_field"] %></td>
                    <td class="py-1.5">
                      <.confidence_bar score={m["confidence"]} />
                    </td>
                    <td class="py-1.5 text-gray-500"><%= m["note"] %></td>
                  </tr>
                <% end %>
              </tbody>
            </table>

            <%!-- Unmapped fields --%>
            <%= if (proposal["proposal_json"]["unmapped_source_fields"] || []) != [] do %>
              <div class="mt-3 text-xs text-red-600">
                Unmapped source fields:
                <%= Enum.join(proposal["proposal_json"]["unmapped_source_fields"], ", ") %>
              </div>
            <% end %>
          </div>

          <%!-- Actions --%>
          <%= if proposal["status"] == "pending_review" do %>
            <div class="px-4 py-3 border-t bg-gray-50 space-y-2">
              <textarea
                phx-blur="set_feedback"
                phx-value-id={proposal["id"]}
                phx-value-value={Map.get(@feedback_map, proposal["id"], "")}
                rows="2"
                placeholder="Optional feedback for revision (leave blank to approve/reject as-is)"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              ><%= Map.get(@feedback_map, proposal["id"], "") %></textarea>
              <div class="flex gap-2">
                <button phx-click="approve" phx-value-id={proposal["id"]}
                        class="btn-primary text-sm">
                  ✓ Approve & Apply
                </button>
                <%= if Map.get(@feedback_map, proposal["id"], "") != "" do %>
                  <button phx-click="modify" phx-value-id={proposal["id"]}
                          class="btn-secondary text-sm">
                    ↩ Request Revision
                  </button>
                <% end %>
                <button phx-click="reject" phx-value-id={proposal["id"]}
                        class="text-red-500 hover:text-red-700 text-sm">
                  ✕ Reject
                </button>
              </div>
            </div>
          <% end %>
        </div>
      <% end %>
    </div>
    """
  end

  defp proposal_type_class("initial_mapping"), do: "bg-blue-100 text-blue-700"
  defp proposal_type_class("drift"), do: "bg-orange-100 text-orange-700"
  defp proposal_type_class("failure"), do: "bg-red-100 text-red-700"
  defp proposal_type_class(_), do: "bg-gray-100 text-gray-700"

  defp confidence_bar(assigns) do
    pct = round((assigns.score || 0) * 100)
    color = cond do
      pct >= 90 -> "bg-green-400"
      pct >= 70 -> "bg-yellow-400"
      true -> "bg-red-400"
    end
    assigns = assign(assigns, pct: pct, color: color)

    ~H"""
    <div class="flex items-center gap-1">
      <div class="w-16 bg-gray-200 rounded-full h-1.5">
        <div class={"h-1.5 rounded-full #{@color}"} style={"width: #{@pct}%"}></div>
      </div>
      <span class="text-gray-500"><%= @pct %>%</span>
    </div>
    """
  end
end
