defmodule NexusUi.ApiClient do
  @moduledoc """
  HTTP client for communicating with the Python FastAPI backend.

  All ETL operations, pipeline management, schema discovery, agent workflows,
  and sync event queries are delegated to FastAPI. This module is the single
  point of contact between Phoenix and the Python layer.

  Uses Req (built on Finch) for async-friendly HTTP with built-in retries,
  JSON encoding/decoding, and structured error handling.
  """

  @type api_result :: {:ok, map() | list()} | {:error, api_error()}
  @type api_error :: %{status: integer(), body: term(), reason: atom()}

  defp base_url do
    Application.get_env(:nexus_ui, :api)[:base_url]
  end

  defp timeout do
    Application.get_env(:nexus_ui, :api)[:timeout] || 30_000
  end

  defp client do
    Req.new(
      base_url: base_url(),
      receive_timeout: timeout(),
      headers: [{"content-type", "application/json"}, {"accept", "application/json"}],
      retry: :transient,
      max_retries: 2
    )
  end

  # ── Connectors ──────────────────────────────────────────────────────────────

  def list_connectors, do: get("/api/v1/connectors")
  def get_connector(id), do: get("/api/v1/connectors/#{id}")
  def create_connector(params), do: post("/api/v1/connectors", params)
  def update_connector(id, params), do: put("/api/v1/connectors/#{id}", params)
  def delete_connector(id), do: delete("/api/v1/connectors/#{id}")
  def test_connector(id), do: post("/api/v1/connectors/#{id}/test", %{})

  def list_connector_types do
    get("/api/v1/connectors/types")
  end

  # ── Pipelines ───────────────────────────────────────────────────────────────

  def list_pipelines(params \\ %{}), do: get("/api/v1/pipelines", params)
  def get_pipeline(id), do: get("/api/v1/pipelines/#{id}")
  def create_pipeline(params), do: post("/api/v1/pipelines", params)
  def update_pipeline(id, params), do: put("/api/v1/pipelines/#{id}", params)
  def delete_pipeline(id), do: delete("/api/v1/pipelines/#{id}")
  def start_pipeline(id), do: post("/api/v1/pipelines/#{id}/start", %{})
  def pause_pipeline(id), do: post("/api/v1/pipelines/#{id}/pause", %{})
  def run_pipeline_now(id), do: post("/api/v1/pipelines/#{id}/run", %{})

  # ── Schema Registry ─────────────────────────────────────────────────────────

  def list_schemas(connector_id), do: get("/api/v1/schemas/#{connector_id}")
  def get_schema(connector_id, entity), do: get("/api/v1/schemas/#{connector_id}/#{entity}")
  def trigger_schema_discovery(connector_id), do: post("/api/v1/schemas/#{connector_id}/discover", %{})
  def list_schema_diffs(connector_id, entity), do: get("/api/v1/schemas/#{connector_id}/#{entity}/diffs")

  # ── Mappings ────────────────────────────────────────────────────────────────

  def list_mappings(pipeline_id), do: get("/api/v1/pipelines/#{pipeline_id}/mappings")
  def upsert_mapping(pipeline_id, params), do: post("/api/v1/pipelines/#{pipeline_id}/mappings", params)
  def delete_mapping(pipeline_id, mapping_id), do: delete("/api/v1/pipelines/#{pipeline_id}/mappings/#{mapping_id}")

  # ── Transformations ─────────────────────────────────────────────────────────

  def get_transformation(pipeline_id), do: get("/api/v1/pipelines/#{pipeline_id}/transformation")
  def update_transformation(pipeline_id, params), do: put("/api/v1/pipelines/#{pipeline_id}/transformation", params)

  def test_transformation(pipeline_id, record) do
    post("/api/v1/pipelines/#{pipeline_id}/transformation/test", %{record: record})
  end

  def regenerate_transformation(pipeline_id) do
    post("/api/v1/pipelines/#{pipeline_id}/transformation/regenerate", %{})
  end

  # ── Agent ───────────────────────────────────────────────────────────────────

  def list_proposals(params \\ %{}), do: get("/api/v1/agent/proposals", params)
  def get_proposal(id), do: get("/api/v1/agent/proposals/#{id}")

  def review_proposal(id, decision, feedback \\ nil) do
    post("/api/v1/agent/proposals/#{id}/review", %{
      decision: decision,
      feedback: feedback
    })
  end

  def trigger_schema_mapping(pipeline_id) do
    post("/api/v1/agent/run", %{trigger_type: "schema_mapping", pipeline_id: pipeline_id})
  end

  def trigger_healing(pipeline_id) do
    post("/api/v1/agent/run", %{trigger_type: "healing", pipeline_id: pipeline_id})
  end

  def get_agent_run(run_id), do: get("/api/v1/agent/runs/#{run_id}")

  # ── Sync Events ─────────────────────────────────────────────────────────────

  def list_sync_events(params \\ %{}), do: get("/api/v1/sync-events", params)
  def get_pipeline_runs(pipeline_id, params \\ %{}) do
    get("/api/v1/pipelines/#{pipeline_id}/runs", params)
  end

  # ── Health ──────────────────────────────────────────────────────────────────

  def health_check, do: get("/health")

  # ── Private HTTP helpers ─────────────────────────────────────────────────────

  defp get(path, params \\ %{}) do
    client()
    |> Req.get(url: path, params: params)
    |> handle_response()
  end

  defp post(path, body) do
    client()
    |> Req.post(url: path, json: body)
    |> handle_response()
  end

  defp put(path, body) do
    client()
    |> Req.put(url: path, json: body)
    |> handle_response()
  end

  defp delete(path) do
    client()
    |> Req.delete(url: path)
    |> handle_response()
  end

  defp handle_response({:ok, %Req.Response{status: status, body: body}})
       when status in 200..299 do
    {:ok, body}
  end

  defp handle_response({:ok, %Req.Response{status: status, body: body}}) do
    {:error, %{status: status, body: body, reason: :api_error}}
  end

  defp handle_response({:error, %Req.TransportError{reason: reason}}) do
    {:error, %{status: 0, body: nil, reason: reason}}
  end

  defp handle_response({:error, reason}) do
    {:error, %{status: 0, body: nil, reason: reason}}
  end
end
