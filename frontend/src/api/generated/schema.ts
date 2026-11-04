export interface paths {
    "/api/v1/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Audit Logs */
        get: operations["list_audit_logs_api_v1_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/forgot-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Forgot Password */
        post: operations["forgot_password_api_v1_auth_forgot_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reset Password */
        post: operations["reset_password_api_v1_auth_reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/signup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Signup */
        post: operations["signup_api_v1_auth_signup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_api_v1_conversations_get"];
        put?: never;
        /** Create Conversation */
        post: operations["create_conversation_api_v1_conversations_post"];
        /** Delete All Conversations */
        delete: operations["delete_all_conversations_api_v1_conversations_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Conversation */
        get: operations["get_conversation_api_v1_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /** Delete Conversation */
        delete: operations["delete_conversation_api_v1_conversations__conversation_id__delete"];
        options?: never;
        head?: never;
        /** Rename Conversation */
        patch: operations["rename_conversation_api_v1_conversations__conversation_id__patch"];
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Messages */
        get: operations["list_messages_api_v1_conversations__conversation_id__messages_get"];
        put?: never;
        /** Submit Message */
        post: operations["submit_message_api_v1_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages/{message_id}/clarification-answers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Answer Clarification */
        post: operations["answer_clarification_api_v1_conversations__conversation_id__messages__message_id__clarification_answers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages/{message_id}/verification": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Verify Message */
        patch: operations["verify_message_api_v1_conversations__conversation_id__messages__message_id__verification_patch"];
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/table-scope": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Table Scope */
        put: operations["update_table_scope_api_v1_conversations__conversation_id__table_scope_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboards": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Dashboards */
        get: operations["list_dashboards_api_v1_dashboards_get"];
        put?: never;
        /** Create Dashboard */
        post: operations["create_dashboard_api_v1_dashboards_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboards/widgets/{widget_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Widget */
        delete: operations["delete_widget_api_v1_dashboards_widgets__widget_id__delete"];
        options?: never;
        head?: never;
        /** Update Widget */
        patch: operations["update_widget_api_v1_dashboards_widgets__widget_id__patch"];
        trace?: never;
    };
    "/api/v1/dashboards/widgets/{widget_id}/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh Widget */
        post: operations["refresh_widget_api_v1_dashboards_widgets__widget_id__refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboards/{dashboard_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Dashboard */
        get: operations["get_dashboard_api_v1_dashboards__dashboard_id__get"];
        put?: never;
        post?: never;
        /** Delete Dashboard */
        delete: operations["delete_dashboard_api_v1_dashboards__dashboard_id__delete"];
        options?: never;
        head?: never;
        /** Update Dashboard */
        patch: operations["update_dashboard_api_v1_dashboards__dashboard_id__patch"];
        trace?: never;
    };
    "/api/v1/dashboards/{dashboard_id}/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh Dashboard */
        post: operations["refresh_dashboard_api_v1_dashboards__dashboard_id__refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboards/{dashboard_id}/widgets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Widget */
        post: operations["add_widget_api_v1_dashboards__dashboard_id__widgets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Data Sources */
        get: operations["list_data_sources_api_v1_data_sources_get"];
        put?: never;
        /** Create Relational Data Source */
        post: operations["create_relational_data_source_api_v1_data_sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/excel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Excel Data Source */
        post: operations["create_excel_data_source_api_v1_data_sources_excel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/power-bi": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Source */
        post: operations["create_source_api_v1_data_sources_power_bi_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{data_source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Data Source */
        get: operations["get_data_source_api_v1_data_sources__data_source_id__get"];
        put?: never;
        post?: never;
        /** Delete Data Source */
        delete: operations["delete_data_source_api_v1_data_sources__data_source_id__delete"];
        options?: never;
        head?: never;
        /** Update Data Source */
        patch: operations["update_data_source_api_v1_data_sources__data_source_id__patch"];
        trace?: never;
    };
    "/api/v1/data-sources/{data_source_id}/excel/replace": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Replace Excel Data Source */
        post: operations["replace_excel_data_source_api_v1_data_sources__data_source_id__excel_replace_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{data_source_id}/schema": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Inspect Data Source */
        get: operations["inspect_data_source_api_v1_data_sources__data_source_id__schema_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{data_source_id}/tables": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Source Tables */
        get: operations["list_source_tables_api_v1_data_sources__data_source_id__tables_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{data_source_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Test Data Source */
        post: operations["test_data_source_api_v1_data_sources__data_source_id__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{source_id}/power-bi/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_data_sources__source_id__power_bi_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources/{source_id}/power-bi/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Reports */
        get: operations["reports_api_v1_data_sources__source_id__power_bi_reports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/exports/excel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Export Excel */
        post: operations["export_excel_api_v1_exports_excel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/instructions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Instructions */
        get: operations["list_instructions_api_v1_instructions_get"];
        put?: never;
        /** Create Instruction */
        post: operations["create_instruction_api_v1_instructions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/instructions/{instruction_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Instruction */
        get: operations["get_instruction_api_v1_instructions__instruction_id__get"];
        put?: never;
        post?: never;
        /** Delete Instruction */
        delete: operations["delete_instruction_api_v1_instructions__instruction_id__delete"];
        options?: never;
        head?: never;
        /** Update Instruction */
        patch: operations["update_instruction_api_v1_instructions__instruction_id__patch"];
        trace?: never;
    };
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Jobs */
        get: operations["list_jobs_api_v1_jobs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job */
        get: operations["get_job_api_v1_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/artifacts/{artifact_id}/html": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Html Artifact
         * @description Serve a shareable POC HTML artifact; UUIDs are the public capability URL.
         */
        get: operations["get_html_artifact_api_v1_jobs__job_id__artifacts__artifact_id__html_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/artifacts/{artifact_id}/matrix/excel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Export Matrix */
        post: operations["export_matrix_api_v1_jobs__job_id__artifacts__artifact_id__matrix_excel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/artifacts/{artifact_id}/rows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Table Rows */
        get: operations["list_table_rows_api_v1_jobs__job_id__artifacts__artifact_id__rows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/artifacts/{artifact_id}/table/excel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Table
         * @description Export every stored row in the viewer's current sort and search.
         */
        post: operations["export_table_api_v1_jobs__job_id__artifacts__artifact_id__table_excel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Job */
        post: operations["cancel_job_api_v1_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Job Events */
        get: operations["job_events_api_v1_jobs__job_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/execution": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job Execution Trace */
        get: operations["get_job_execution_trace_api_v1_jobs__job_id__execution_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/annotations/{annotation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Annotation */
        delete: operations["delete_annotation_api_v1_knowledge_annotations__annotation_id__delete"];
        options?: never;
        head?: never;
        /** Update Annotation */
        patch: operations["update_annotation_api_v1_knowledge_annotations__annotation_id__patch"];
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Knowledge Status */
        get: operations["get_knowledge_status_api_v1_knowledge_data_sources__data_source_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/annotations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Annotations */
        get: operations["list_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_get"];
        put?: never;
        /** Create Annotation */
        post: operations["create_annotation_api_v1_knowledge_data_sources__data_source_id__annotations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/annotations/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export Annotations */
        get: operations["export_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/annotations/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Annotations */
        post: operations["import_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Documents */
        get: operations["list_documents_api_v1_knowledge_data_sources__data_source_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Document */
        get: operations["get_document_api_v1_knowledge_data_sources__data_source_id__documents__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Knowledge */
        post: operations["generate_knowledge_api_v1_knowledge_data_sources__data_source_id__generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/index": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Index */
        get: operations["get_index_api_v1_knowledge_data_sources__data_source_id__index_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/schema-compact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Compact Schema */
        get: operations["get_compact_schema_api_v1_knowledge_data_sources__data_source_id__schema_compact_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/table": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Table Document */
        get: operations["get_table_document_api_v1_knowledge_data_sources__data_source_id__table_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/data-sources/{data_source_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Versions */
        get: operations["list_versions_api_v1_knowledge_data_sources__data_source_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/connections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Connections */
        get: operations["list_connections_api_v1_models_connections_get"];
        put?: never;
        /** Create Connection */
        post: operations["create_connection_api_v1_models_connections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/connections/{connection_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Connection */
        get: operations["get_connection_api_v1_models_connections__connection_id__get"];
        put?: never;
        post?: never;
        /** Delete Connection */
        delete: operations["delete_connection_api_v1_models_connections__connection_id__delete"];
        options?: never;
        head?: never;
        /** Update Connection */
        patch: operations["update_connection_api_v1_models_connections__connection_id__patch"];
        trace?: never;
    };
    "/api/v1/models/connections/{connection_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Test Connection */
        post: operations["test_connection_api_v1_models_connections__connection_id__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Profiles */
        get: operations["list_profiles_api_v1_models_profiles_get"];
        put?: never;
        /** Create Profile */
        post: operations["create_profile_api_v1_models_profiles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/profiles/default": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Default Profile */
        get: operations["get_default_profile_api_v1_models_profiles_default_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/profiles/{profile_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Profile */
        get: operations["get_profile_api_v1_models_profiles__profile_id__get"];
        put?: never;
        post?: never;
        /** Delete Profile */
        delete: operations["delete_profile_api_v1_models_profiles__profile_id__delete"];
        options?: never;
        head?: never;
        /** Update Profile */
        patch: operations["update_profile_api_v1_models_profiles__profile_id__patch"];
        trace?: never;
    };
    "/api/v1/models/profiles/{profile_id}/default": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Set Default Profile */
        post: operations["set_default_profile_api_v1_models_profiles__profile_id__default_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Operational Status */
        get: operations["operational_status_api_v1_ops_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Organizations */
        get: operations["list_organizations_api_v1_organizations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Organization */
        get: operations["current_organization_api_v1_organizations_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations/{organization_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Organization */
        patch: operations["update_organization_api_v1_organizations__organization_id__patch"];
        trace?: never;
    };
    "/api/v1/power-bi/connections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Connections */
        get: operations["connections_api_v1_power_bi_connections_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/connections/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Connect */
        post: operations["connect_api_v1_power_bi_connections_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/connections/{connection_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Disconnect */
        delete: operations["disconnect_api_v1_power_bi_connections__connection_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/features": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Features */
        get: operations["features_api_v1_power_bi_features_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/reports/discover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Discover */
        post: operations["discover_api_v1_power_bi_reports_discover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/reports/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve */
        post: operations["resolve_api_v1_power_bi_reports_resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/power-bi/reports/{binding_id}/embed-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Embed */
        post: operations["embed_api_v1_power_bi_reports__binding_id__embed_config_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AnswerReviewCounts */
        AnswerReviewCounts: {
            /**
             * Correct
             * @default 0
             */
            correct: number;
            /**
             * Incorrect
             * @default 0
             */
            incorrect: number;
            /**
             * Partially Correct
             * @default 0
             */
            partially_correct: number;
            /**
             * Total
             * @default 0
             */
            total: number;
            /**
             * Unreviewed
             * @default 0
             */
            unreviewed: number;
        };
        /** AuditLogResponse */
        AuditLogResponse: {
            /** Action */
            action: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Resource Id */
            resource_id: string | null;
            /** Resource Type */
            resource_type: string;
            /** User Id */
            user_id: string | null;
        };
        /** Body_create_excel_data_source_api_v1_data_sources_excel_post */
        Body_create_excel_data_source_api_v1_data_sources_excel_post: {
            /** File */
            file: string;
            /** Name */
            name: string;
        };
        /** Body_import_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_import_post */
        Body_import_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_import_post: {
            /** Files */
            files: string[];
        };
        /** Body_replace_excel_data_source_api_v1_data_sources__data_source_id__excel_replace_post */
        Body_replace_excel_data_source_api_v1_data_sources__data_source_id__excel_replace_post: {
            /** File */
            file: string;
        };
        /** ClarificationAnswer */
        ClarificationAnswer: {
            /** Other Text */
            other_text?: string | null;
            /** Question Id */
            question_id: string;
            /** Selected */
            selected?: string[];
            /** Text */
            text?: string | null;
        };
        /** ClarificationAnswers */
        ClarificationAnswers: {
            /** Answers */
            answers: components["schemas"]["ClarificationAnswer"][];
        };
        /** ColumnMetadataResponse */
        ColumnMetadataResponse: {
            /** Default */
            default: string | null;
            /** Name */
            name: string;
            /** Native Type */
            native_type: string;
            /** Nullable */
            nullable: boolean | null;
        };
        /**
         * CompactSchemaResponse
         * @description Every table and view of the current knowledge version, one compact line each.
         */
        CompactSchemaResponse: {
            /**
             * Knowledge Version Id
             * Format: uuid
             */
            knowledge_version_id: string;
            /** Table Count */
            table_count: number;
            /** Text */
            text: string;
        };
        /** ConnectionDiagnostics */
        ConnectionDiagnostics: {
            /** Category */
            category: string;
            /** Driver Message */
            driver_message: string;
            /** Error Number */
            error_number?: number | null;
            /** Job Id */
            job_id?: string | null;
            /** Message */
            message: string;
            /** Next Steps */
            next_steps: string[];
            /** Sqlstate */
            sqlstate?: string | null;
            /** Stage */
            stage: string;
        };
        /** ConnectionResponse */
        ConnectionResponse: {
            /** Display Name */
            display_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
            /** Tenant Id */
            tenant_id: string;
        };
        /** ConnectionStart */
        ConnectionStart: {
            /** Authorization Url */
            authorization_url: string;
        };
        /** ConversationCreate */
        ConversationCreate: {
            /** Data Source Ids */
            data_source_ids: string[];
            /** Model Profile Id */
            model_profile_id?: string | null;
            /** Table Scope */
            table_scope?: components["schemas"]["SourceTableScope"][];
            /** Title */
            title?: string | null;
        };
        /**
         * ConversationPage
         * @description Conversations, most recently updated first.
         */
        ConversationPage: {
            /** Has More */
            has_more: boolean;
            /** Items */
            items: components["schemas"]["ConversationResponse"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ConversationRename */
        ConversationRename: {
            /** Title */
            title: string;
        };
        /** ConversationResponse */
        ConversationResponse: {
            answer_review_counts?: components["schemas"]["AnswerReviewCounts"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Data Source Ids */
            data_source_ids?: string[];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Model Profile Id */
            model_profile_id: string | null;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Table Scope */
            table_scope?: components["schemas"]["SourceTableScope"][];
            /** Title */
            title: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ConversationTableScopeUpdate */
        ConversationTableScopeUpdate: {
            /** Table Scope */
            table_scope: components["schemas"]["SourceTableScope"][];
        };
        /** DashboardCreate */
        DashboardCreate: {
            /** Description */
            description?: string | null;
            /** Title */
            title: string;
        };
        /** DashboardDetailResponse */
        DashboardDetailResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Widget Count
             * @default 0
             */
            widget_count: number;
            /** Widgets */
            widgets?: components["schemas"]["DashboardWidgetResponse"][];
        };
        /** DashboardRefreshResponse */
        DashboardRefreshResponse: {
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
        };
        /** DashboardResponse */
        DashboardResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Widget Count
             * @default 0
             */
            widget_count: number;
        };
        /** DashboardUpdate */
        DashboardUpdate: {
            /** Description */
            description?: string | null;
            /** Title */
            title?: string | null;
        };
        /** DashboardWidgetCreate */
        DashboardWidgetCreate: {
            /** Layout Config */
            layout_config?: {
                [key: string]: unknown;
            };
            /**
             * Source Job Id
             * Format: uuid
             */
            source_job_id: string;
            /**
             * Source Sql Execution Id
             * Format: uuid
             */
            source_sql_execution_id: string;
            /** Title */
            title?: string | null;
            /** Visualization Config */
            visualization_config?: {
                [key: string]: unknown;
            };
            /**
             * Widget Type
             * @enum {string}
             */
            widget_type: "metric" | "table" | "bar" | "line" | "area" | "pie" | "donut" | "combo";
        };
        /** DashboardWidgetResponse */
        DashboardWidgetResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created From Job Id */
            created_from_job_id: string | null;
            /** Created From Sql Execution Id */
            created_from_sql_execution_id: string | null;
            /**
             * Dashboard Id
             * Format: uuid
             */
            dashboard_id: string;
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Refresh Job Id */
            last_refresh_job_id: string | null;
            /** Last Refreshed At */
            last_refreshed_at: string | null;
            /** Latest Artifact */
            latest_artifact?: {
                [key: string]: unknown;
            } | null;
            /** Layout Config */
            layout_config: {
                [key: string]: unknown;
            };
            /** Question */
            question: string | null;
            /** Sql Text */
            sql_text: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Visualization Config */
            visualization_config: {
                [key: string]: unknown;
            };
            /** Widget Type */
            widget_type: string;
        };
        /** DashboardWidgetUpdate */
        DashboardWidgetUpdate: {
            /** Enabled */
            enabled?: boolean | null;
            /** Layout Config */
            layout_config?: {
                [key: string]: unknown;
            } | null;
            /** Title */
            title?: string | null;
            /** Visualization Config */
            visualization_config?: {
                [key: string]: unknown;
            } | null;
        };
        /** DataSourceFileResponse */
        DataSourceFileResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Original Filename */
            original_filename: string;
            /** Sha256 */
            sha256: string;
            /** Sheet Mapping */
            sheet_mapping: {
                [key: string]: unknown;
            }[];
            /** Size Bytes */
            size_bytes: number;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** DataSourceResponse */
        DataSourceResponse: {
            active_file?: components["schemas"]["DataSourceFileResponse"] | null;
            /** Config */
            config: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Display Type */
            display_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            last_connection_diagnostics?: components["schemas"]["ConnectionDiagnostics"] | null;
            /** Last Error Code */
            last_error_code: string | null;
            /** Last Tested At */
            last_tested_at: string | null;
            /** Name */
            name: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** DataSourceUpdate */
        DataSourceUpdate: {
            /** Config */
            config?: {
                [key: string]: unknown;
            } | null;
            credentials?: components["schemas"]["DatabaseCredentials"] | null;
            /** Name */
            name?: string | null;
            /** Status */
            status?: ("active" | "disabled") | null;
        };
        /** DatabaseCredentials */
        DatabaseCredentials: {
            /**
             * Password
             * Format: password
             */
            password: string;
            /** Username */
            username: string;
        };
        /** DaxExecutionResponse */
        DaxExecutionResponse: {
            /** Columns */
            columns: string[] | null;
            /** Context */
            context: {
                [key: string]: unknown;
            };
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /** Dax Text */
            dax_text: string;
            /** Duration Ms */
            duration_ms: number | null;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Result Bytes */
            result_bytes: number | null;
            /** Row Count */
            row_count: number | null;
            /** Semantic Model Id */
            semantic_model_id: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
            /**
             * Tool Execution Id
             * Format: uuid
             */
            tool_execution_id: string;
            /** Truncated */
            truncated: boolean;
        };
        /** EmbedConfiguration */
        EmbedConfiguration: {
            /** Access Token */
            access_token: string;
            /** Embed Url */
            embed_url: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Report Id */
            report_id: string;
            /**
             * Token Type
             * @default Aad
             * @constant
             */
            token_type: "Aad";
        };
        /** ExcelTableExport */
        ExcelTableExport: {
            /** Headers */
            headers: string[];
            /** Rows */
            rows: (string | number | boolean | null)[][];
            /**
             * Title
             * @default Table
             */
            title: string;
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /** ExcelUploadResponse */
        ExcelUploadResponse: {
            data_source: components["schemas"]["DataSourceResponse"];
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
        };
        /** ForeignKeyMetadataResponse */
        ForeignKeyMetadataResponse: {
            /** Constrained Columns */
            constrained_columns: string[];
            /** Referred Columns */
            referred_columns: string[];
            /** Referred Schema */
            referred_schema: string | null;
            /** Referred Table */
            referred_table: string;
        };
        /** ForgotPasswordRequest */
        ForgotPasswordRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** InstructionCreate */
        InstructionCreate: {
            /** Command */
            command?: string | null;
            /** Content */
            content: string;
            /** Description */
            description?: string | null;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /**
             * Is Default
             * @default false
             */
            is_default: boolean;
            /** Name */
            name: string;
            /** Prompt Template */
            prompt_template?: string | null;
        };
        /** InstructionResponse */
        InstructionResponse: {
            /** Command */
            command?: string | null;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Description */
            description?: string | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Default */
            is_default: boolean;
            /** Name */
            name: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Prompt Template */
            prompt_template?: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** InstructionUpdate */
        InstructionUpdate: {
            /** Command */
            command?: string | null;
            /** Content */
            content?: string | null;
            /** Description */
            description?: string | null;
            /** Enabled */
            enabled?: boolean | null;
            /** Is Default */
            is_default?: boolean | null;
            /** Name */
            name?: string | null;
            /** Prompt Template */
            prompt_template?: string | null;
        };
        /** JobAcceptedResponse */
        JobAcceptedResponse: {
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
        };
        /** JobArtifactResponse */
        JobArtifactResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Kind */
            kind: string;
            /** Name */
            name: string | null;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Source Dax Execution Id */
            source_dax_execution_id?: string | null;
            /** Source Sql Execution Id */
            source_sql_execution_id: string | null;
            table_rows?: components["schemas"]["TableRowsInfo"] | null;
        };
        /** JobExecutionTraceResponse */
        JobExecutionTraceResponse: {
            /** Artifacts */
            artifacts?: components["schemas"]["JobArtifactResponse"][];
            /** Dax */
            dax?: components["schemas"]["DaxExecutionResponse"][];
            /** Models */
            models?: components["schemas"]["ModelExecutionResponse"][];
            /** Sql */
            sql?: components["schemas"]["SQLExecutionResponse"][];
            /** Tools */
            tools?: components["schemas"]["ToolExecutionResponse"][];
        };
        /** JobResponse */
        JobResponse: {
            /** Attempt Count */
            attempt_count: number;
            /** Cancel Requested At */
            cancel_requested_at: string | null;
            /** Conversation Id */
            conversation_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Duration Ms */
            duration_ms?: number | null;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input */
            input: {
                [key: string]: unknown;
            };
            /** Job Type */
            job_type: string;
            /** Max Attempts */
            max_attempts: number;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /**
             * Requested By
             * Format: uuid
             */
            requested_by: string;
            /** Result */
            result: {
                [key: string]: unknown;
            } | null;
            /** Started At */
            started_at: string | null;
            /** Status */
            status: string;
        };
        /** KnowledgeAnnotationCreate */
        KnowledgeAnnotationCreate: {
            /** Content */
            content: string;
            /** Scope Key */
            scope_key?: string | null;
            /**
             * Scope Type
             * @enum {string}
             */
            scope_type: "datasource" | "table" | "column" | "metric";
            /** Title */
            title?: string | null;
        };
        /** KnowledgeAnnotationResponse */
        KnowledgeAnnotationResponse: {
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Knowledge Base Id
             * Format: uuid
             */
            knowledge_base_id: string;
            /** Scope Key */
            scope_key: string | null;
            /** Scope Type */
            scope_type: string;
            /** Title */
            title: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** KnowledgeAnnotationUpdate */
        KnowledgeAnnotationUpdate: {
            /** Content */
            content: string;
            /** Title */
            title?: string | null;
        };
        /** KnowledgeDocumentResponse */
        KnowledgeDocumentResponse: {
            /** Content Markdown */
            content_markdown: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Key */
            document_key: string;
            /** Document Type */
            document_type: string;
            /** Estimated Tokens */
            estimated_tokens: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /** Title */
            title: string;
        };
        /** KnowledgeDocumentSummary */
        KnowledgeDocumentSummary: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Key */
            document_key: string;
            /** Document Type */
            document_type: string;
            /** Estimated Tokens */
            estimated_tokens: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /** Title */
            title: string;
        };
        /**
         * KnowledgeImportItem
         * @description What happened (or, for a dry run, would happen) to one uploaded file.
         */
        KnowledgeImportItem: {
            /** Filename */
            filename: string;
            /** Message */
            message?: string | null;
            /** Scope Key */
            scope_key?: string | null;
            /** Scope Type */
            scope_type?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "created" | "updated" | "skipped" | "error";
            /** Title */
            title?: string | null;
        };
        /** KnowledgeImportResponse */
        KnowledgeImportResponse: {
            /** Created */
            created: number;
            /** Dry Run */
            dry_run: boolean;
            /** Failed */
            failed: number;
            /** Items */
            items: components["schemas"]["KnowledgeImportItem"][];
            /** Skipped */
            skipped: number;
            /** Updated */
            updated: number;
        };
        /** KnowledgeJobResponse */
        KnowledgeJobResponse: {
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /**
             * Knowledge Base Id
             * Format: uuid
             */
            knowledge_base_id: string;
        };
        /** KnowledgeStatusResponse */
        KnowledgeStatusResponse: {
            /** Current Version Id */
            current_version_id: string | null;
            /** Current Version Number */
            current_version_number: number | null;
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /** Generated At */
            generated_at: string | null;
            /** Knowledge Base Id */
            knowledge_base_id: string | null;
            /** Last Error Code */
            last_error_code: string | null;
            /** Object Count */
            object_count: number | null;
            /** Schema Fingerprint */
            schema_fingerprint: string | null;
            /** Status */
            status: string;
        };
        /** KnowledgeVersionResponse */
        KnowledgeVersionResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Generated By Job Id */
            generated_by_job_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Knowledge Base Id
             * Format: uuid
             */
            knowledge_base_id: string;
            /** Schema Fingerprint */
            schema_fingerprint: string;
            /** Version Number */
            version_number: number;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
        };
        /** LogoutRequest */
        LogoutRequest: {
            /** Refresh Token */
            refresh_token: string;
        };
        /** MSSQLConfig */
        MSSQLConfig: {
            /**
             * Authentication Mode
             * @default sql
             * @enum {string}
             */
            authentication_mode: "sql" | "windows";
            /** Database */
            database: string;
            /**
             * Encrypt
             * @default true
             */
            encrypt: boolean;
            /** Host */
            host: string;
            /**
             * Odbc Driver
             * @default ODBC Driver 18 for SQL Server
             */
            odbc_driver: string;
            /**
             * Port
             * @default 1433
             */
            port: number;
            /**
             * Schema Name
             * @default dbo
             */
            schema_name: string;
            /**
             * Trust Server Certificate
             * @default false
             */
            trust_server_certificate: boolean;
        };
        /** MSSQLDataSourceCreate */
        MSSQLDataSourceCreate: {
            config: components["schemas"]["MSSQLConfig"];
            credentials?: components["schemas"]["DatabaseCredentials"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "mssql";
            /** Name */
            name: string;
        };
        /** MatrixViewState */
        MatrixViewState: {
            /** Collapsed Columns */
            collapsed_columns?: string[];
            /** Collapsed Rows */
            collapsed_rows?: string[];
        };
        /** MessageAcceptedResponse */
        MessageAcceptedResponse: {
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
        };
        /** MessageCreate */
        MessageCreate: {
            /** Content */
            content: string;
            /** Model Profile Id */
            model_profile_id?: string | null;
            power_bi_context?: components["schemas"]["ReportContext"] | null;
            /** Reasoning Effort */
            reasoning_effort?: ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max") | null;
        };
        /**
         * MessagePage
         * @description Chronological messages; next_cursor continues toward older messages.
         */
        MessagePage: {
            /** Has More */
            has_more: boolean;
            /** Items */
            items: components["schemas"]["app__conversations__schemas__MessageResponse"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** MessageVerificationUpdate */
        MessageVerificationUpdate: {
            /** Verification Percentage */
            verification_percentage?: number | null;
            /** Verification Status */
            verification_status: ("CORRECT" | "PARTIALLY_CORRECT" | "INCORRECT") | null;
            /** Verification Summary */
            verification_summary?: string | null;
        };
        /** ModelConnectionCreate */
        ModelConnectionCreate: {
            /** Api Key */
            api_key?: string | null;
            /** Base Url */
            base_url: string;
            /** Name */
            name: string;
        };
        /** ModelConnectionResponse */
        ModelConnectionResponse: {
            /** Base Url */
            base_url: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Has Api Key
             * @default false
             */
            has_api_key: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Error Code */
            last_error_code: string | null;
            /** Last Tested At */
            last_tested_at: string | null;
            /** Name */
            name: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ModelConnectionTestResponse */
        ModelConnectionTestResponse: {
            /** Model Count */
            model_count: number;
            /** Ok */
            ok: boolean;
            /** Sample Models */
            sample_models: string[];
            /**
             * Tested At
             * Format: date-time
             */
            tested_at: string;
        };
        /** ModelConnectionUpdate */
        ModelConnectionUpdate: {
            /** Api Key */
            api_key?: string | null;
            /** Base Url */
            base_url?: string | null;
            /**
             * Clear Api Key
             * @default false
             */
            clear_api_key: boolean;
            /** Name */
            name?: string | null;
            /** Status */
            status?: string | null;
        };
        /** ModelExecutionResponse */
        ModelExecutionResponse: {
            /** Cached Input Price Per Million */
            cached_input_price_per_million?: number | null;
            /** Cached Input Tokens */
            cached_input_tokens?: number | null;
            /** Cost */
            cost?: number | null;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Price Per Million */
            input_price_per_million?: number | null;
            /** Input Tokens */
            input_tokens: number | null;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Model Name */
            model_name: string;
            /**
             * Model Profile Id
             * Format: uuid
             */
            model_profile_id: string;
            /** Output Price Per Million */
            output_price_per_million?: number | null;
            /** Output Tokens */
            output_tokens: number | null;
            /** Phase */
            phase: string;
            /** Provider Error Response */
            provider_error_response?: {
                [key: string]: unknown;
            } | null;
            /** Reasoning Effort */
            reasoning_effort?: string | null;
            /** Sequence */
            sequence: number;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
            /** Total Tokens */
            total_tokens: number | null;
        };
        /** ModelProfileCreate */
        ModelProfileCreate: {
            /**
             * Cached Input Price Per Million
             * @description USD per 1M cached input tokens.
             */
            cached_input_price_per_million?: number | null;
            /**
             * Connection Id
             * Format: uuid
             */
            connection_id: string;
            /** Display Name */
            display_name: string;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /**
             * Input Price Per Million
             * @description USD per 1M input tokens.
             */
            input_price_per_million?: number | null;
            /**
             * Is Default
             * @default false
             */
            is_default: boolean;
            /** Model Name */
            model_name: string;
            /**
             * Output Price Per Million
             * @description USD per 1M output tokens.
             */
            output_price_per_million?: number | null;
            /** Settings */
            settings?: {
                [key: string]: unknown;
            };
        };
        /** ModelProfileResponse */
        ModelProfileResponse: {
            /** Cached Input Price Per Million */
            cached_input_price_per_million?: number | null;
            /**
             * Connection Id
             * Format: uuid
             */
            connection_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Default Reasoning Effort */
            readonly default_reasoning_effort: ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max") | null;
            /** Display Name */
            display_name: string;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Price Per Million */
            input_price_per_million?: number | null;
            /** Is Default */
            is_default: boolean;
            /** Model Name */
            model_name: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Output Price Per Million */
            output_price_per_million?: number | null;
            /**
             * Reasoning Efforts
             * @description Efforts a question may choose for this model; empty when it has no effort control.
             */
            readonly reasoning_efforts: ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max")[];
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ModelProfileUpdate */
        ModelProfileUpdate: {
            /**
             * Cached Input Price Per Million
             * @description USD per 1M cached input tokens.
             */
            cached_input_price_per_million?: number | null;
            /** Connection Id */
            connection_id?: string | null;
            /** Display Name */
            display_name?: string | null;
            /** Enabled */
            enabled?: boolean | null;
            /**
             * Input Price Per Million
             * @description USD per 1M input tokens.
             */
            input_price_per_million?: number | null;
            /** Model Name */
            model_name?: string | null;
            /**
             * Output Price Per Million
             * @description USD per 1M output tokens.
             */
            output_price_per_million?: number | null;
            /** Settings */
            settings?: {
                [key: string]: unknown;
            } | null;
        };
        /** MySQLConfig */
        MySQLConfig: {
            /** Database */
            database: string;
            /** Host */
            host: string;
            /**
             * Port
             * @default 3306
             */
            port: number;
            /**
             * Ssl
             * @default false
             */
            ssl: boolean;
        };
        /** MySQLDataSourceCreate */
        MySQLDataSourceCreate: {
            config: components["schemas"]["MySQLConfig"];
            credentials: components["schemas"]["DatabaseCredentials"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "mysql";
            /** Name */
            name: string;
        };
        /** OrganizationResponse */
        OrganizationResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Role */
            role?: string | null;
            /** Slug */
            slug: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** OrganizationUpdateRequest */
        OrganizationUpdateRequest: {
            /** Name */
            name: string;
        };
        /** PostgresConfig */
        PostgresConfig: {
            /** Database */
            database: string;
            /** Host */
            host: string;
            /**
             * Port
             * @default 5432
             */
            port: number;
            /**
             * Schema Name
             * @default public
             */
            schema_name: string;
            /**
             * Ssl Mode
             * @default prefer
             * @enum {string}
             */
            ssl_mode: "disable" | "prefer" | "require" | "verify-ca" | "verify-full";
        };
        /** PostgresDataSourceCreate */
        PostgresDataSourceCreate: {
            config: components["schemas"]["PostgresConfig"];
            credentials: components["schemas"]["DatabaseCredentials"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "postgres";
            /** Name */
            name: string;
        };
        /** PowerBICreate */
        PowerBICreate: {
            /**
             * Embedding Enabled
             * @default true
             */
            embedding_enabled: boolean;
            /** Name */
            name: string;
            /** Report Url */
            report_url: string;
        };
        /** PowerBIFeatures */
        PowerBIFeatures: {
            /** Configured */
            configured: boolean;
            /** Embedding Enabled */
            embedding_enabled: boolean;
            /** Enabled */
            enabled: boolean;
        };
        /** RefreshRequest */
        RefreshRequest: {
            /** Refresh Token */
            refresh_token: string;
        };
        /** ReportCandidate */
        ReportCandidate: {
            /** Name */
            name: string;
            /** Report Id */
            report_id: string;
            /** Semantic Model Id */
            semantic_model_id: string;
            /** Web Url */
            web_url: string;
            /** Workspace Id */
            workspace_id?: string | null;
        };
        /** ReportContext */
        ReportContext: {
            /**
             * Captured At
             * Format: date-time
             */
            captured_at: string;
            /** Filters */
            filters?: {
                [key: string]: unknown;
            }[];
            /**
             * Mode
             * @default report_view
             * @enum {string}
             */
            mode: "report_view" | "model";
            /** Page Display Name */
            page_display_name: string;
            /** Page Name */
            page_name: string;
            /**
             * Report Binding Id
             * Format: uuid
             */
            report_binding_id: string;
            /** Unsupported */
            unsupported?: string[];
        };
        /** ReportLookup */
        ReportLookup: {
            /** Query */
            query: string;
        };
        /** ReportResponse */
        ReportResponse: {
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /** Embedding Enabled */
            embedding_enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Report Id */
            report_id: string;
            /** Web Url */
            web_url: string;
        };
        /** ResetPasswordRequest */
        ResetPasswordRequest: {
            /** New Password */
            new_password: string;
            /** Token */
            token: string;
        };
        /** SQLExecutionResponse */
        SQLExecutionResponse: {
            /** Columns */
            columns: string[] | null;
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /** Duration Ms */
            duration_ms: number | null;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Result Bytes */
            result_bytes: number | null;
            /** Row Count */
            row_count: number | null;
            /** Sql Text */
            sql_text: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
            /**
             * Tool Execution Id
             * Format: uuid
             */
            tool_execution_id: string;
            /** Truncated */
            truncated: boolean;
        };
        /** SchemaMetadataResponse */
        SchemaMetadataResponse: {
            /** Tables */
            tables: components["schemas"]["TableMetadataResponse"][];
        };
        /** SignupRequest */
        SignupRequest: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Organization Name */
            organization_name?: string | null;
            /** Password */
            password: string;
        };
        /** SourceTableScope */
        SourceTableScope: {
            /**
             * Data Source Id
             * Format: uuid
             */
            data_source_id: string;
            /**
             * Mode
             * @default all
             * @enum {string}
             */
            mode: "all" | "selected";
            /** Tables */
            tables?: components["schemas"]["TableIdentifier"][];
        };
        /** TableCatalogItem */
        TableCatalogItem: {
            /** Column Count */
            column_count: number;
            /** Name */
            name: string;
            /** Object Type */
            object_type: string;
            /** Schema */
            schema?: string | null;
        };
        /** TableCatalogResponse */
        TableCatalogResponse: {
            /** Items */
            items: components["schemas"]["TableCatalogItem"][];
            /**
             * Knowledge Version Id
             * Format: uuid
             */
            knowledge_version_id: string;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** TableExcelRequest */
        TableExcelRequest: {
            /**
             * Descending
             * @default false
             */
            descending: boolean;
            /** Headers */
            headers?: string[] | null;
            /**
             * Search
             * @default
             */
            search: string;
            /** Sort */
            sort?: string | null;
            /**
             * Title
             * @default Table
             */
            title: string;
        };
        /** TableIdentifier */
        TableIdentifier: {
            /** Name */
            name: string;
            /** Schema */
            schema?: string | null;
        };
        /** TableMetadataResponse */
        TableMetadataResponse: {
            /** Columns */
            columns: components["schemas"]["ColumnMetadataResponse"][];
            /** Foreign Keys */
            foreign_keys: components["schemas"]["ForeignKeyMetadataResponse"][];
            /** Name */
            name: string;
            /** Object Type */
            object_type: string;
            /** Primary Key */
            primary_key: string[];
            /** Schema */
            schema: string | null;
        };
        /**
         * TableRowsInfo
         * @description Paging state for a table artifact whose rows are trimmed in the execution trace.
         */
        TableRowsInfo: {
            /** Has More */
            has_more: boolean;
            /** Next Cursor */
            next_cursor: string | null;
            /** Stored Row Count */
            stored_row_count: number;
        };
        /** TableRowsPage */
        TableRowsPage: {
            /** Columns */
            columns: string[];
            /** Has More */
            has_more: boolean;
            /** Matching Count */
            matching_count: number;
            /** Next Cursor */
            next_cursor: string | null;
            /** Rows */
            rows: unknown[][];
        };
        /** TokenResponse */
        TokenResponse: {
            /** Access Token */
            access_token: string;
            /** Expires In */
            expires_in: number;
            /** Refresh Token */
            refresh_token: string;
            /**
             * Token Type
             * @default bearer
             */
            token_type: string;
        };
        /** ToolExecutionResponse */
        ToolExecutionResponse: {
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Summary */
            input_summary: {
                [key: string]: unknown;
            };
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Output Summary */
            output_summary: {
                [key: string]: unknown;
            } | null;
            /** Sequence */
            sequence: number;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
            /** Tool Name */
            tool_name: string;
        };
        /** UserResponse */
        UserResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Display Name */
            display_name: string | null;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Email Verified At */
            email_verified_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** MessageResponse */
        app__auth__schemas__MessageResponse: {
            /** Message */
            message: string;
        };
        /** MessageResponse */
        app__conversations__schemas__MessageResponse: {
            /** Content */
            content: string;
            /**
             * Conversation Id
             * Format: uuid
             */
            conversation_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Job Id */
            job_id: string | null;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /** Role */
            role: string;
            /** Verification Percentage */
            verification_percentage?: number | null;
            /** Verification Status */
            verification_status?: ("CORRECT" | "PARTIALLY_CORRECT" | "INCORRECT") | null;
            /** Verification Summary */
            verification_summary?: string | null;
            /** Verified At */
            verified_at?: string | null;
            /** Verified By */
            verified_by?: string | null;
            /** Verified By Name */
            verified_by_name?: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_audit_logs_api_v1_audit_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditLogResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    forgot_password_api_v1_auth_forgot_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ForgotPasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__auth__schemas__MessageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LogoutRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__auth__schemas__MessageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_password_api_v1_auth_reset_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResetPasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__auth__schemas__MessageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    signup_api_v1_auth_signup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_conversations_api_v1_conversations_get: {
        parameters: {
            query?: {
                search?: string;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_conversation_api_v1_conversations_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_all_conversations_api_v1_conversations_delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_conversation_api_v1_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_conversation_api_v1_conversations__conversation_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rename_conversation_api_v1_conversations__conversation_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationRename"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_messages_api_v1_conversations__conversation_id__messages_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessagePage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_message_api_v1_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageAcceptedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    answer_clarification_api_v1_conversations__conversation_id__messages__message_id__clarification_answers_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClarificationAnswers"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageAcceptedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    verify_message_api_v1_conversations__conversation_id__messages__message_id__verification_patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageVerificationUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__conversations__schemas__MessageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_table_scope_api_v1_conversations__conversation_id__table_scope_put: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationTableScopeUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_dashboards_api_v1_dashboards_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_dashboard_api_v1_dashboards_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_widget_api_v1_dashboards_widgets__widget_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                widget_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_widget_api_v1_dashboards_widgets__widget_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                widget_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardWidgetUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardWidgetResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_widget_api_v1_dashboards_widgets__widget_id__refresh_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                widget_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardRefreshResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_dashboard_api_v1_dashboards__dashboard_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                dashboard_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_dashboard_api_v1_dashboards__dashboard_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                dashboard_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_dashboard_api_v1_dashboards__dashboard_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                dashboard_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_dashboard_api_v1_dashboards__dashboard_id__refresh_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                dashboard_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardRefreshResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_widget_api_v1_dashboards__dashboard_id__widgets_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                dashboard_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardWidgetCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardWidgetResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_data_sources_api_v1_data_sources_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSourceResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_relational_data_source_api_v1_data_sources_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PostgresDataSourceCreate"] | components["schemas"]["MySQLDataSourceCreate"] | components["schemas"]["MSSQLDataSourceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_excel_data_source_api_v1_data_sources_excel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_create_excel_data_source_api_v1_data_sources_excel_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExcelUploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_source_api_v1_data_sources_power_bi_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PowerBICreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_data_source_api_v1_data_sources__data_source_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_data_source_api_v1_data_sources__data_source_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_data_source_api_v1_data_sources__data_source_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DataSourceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replace_excel_data_source_api_v1_data_sources__data_source_id__excel_replace_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_replace_excel_data_source_api_v1_data_sources__data_source_id__excel_replace_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAcceptedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    inspect_data_source_api_v1_data_sources__data_source_id__schema_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SchemaMetadataResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_source_tables_api_v1_data_sources__data_source_id__tables_get: {
        parameters: {
            query?: {
                search?: string;
                cursor?: string | null;
                limit?: number;
                knowledge_version_id?: string | null;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableCatalogResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_data_source_api_v1_data_sources__data_source_id__test_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAcceptedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_v1_data_sources__source_id__power_bi_refresh_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reports_api_v1_data_sources__source_id__power_bi_reports_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_excel_api_v1_exports_excel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExcelTableExport"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_instructions_api_v1_instructions_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstructionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_instruction_api_v1_instructions_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstructionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstructionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_instruction_api_v1_instructions__instruction_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                instruction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstructionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_instruction_api_v1_instructions__instruction_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                instruction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_instruction_api_v1_instructions__instruction_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                instruction_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstructionUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstructionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_jobs_api_v1_jobs_get: {
        parameters: {
            query?: {
                status?: string | null;
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_job_api_v1_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_html_artifact_api_v1_jobs__job_id__artifacts__artifact_id__html_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_matrix_api_v1_jobs__job_id__artifacts__artifact_id__matrix_excel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MatrixViewState"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_table_rows_api_v1_jobs__job_id__artifacts__artifact_id__rows_get: {
        parameters: {
            query?: {
                sort?: string | null;
                descending?: boolean;
                search?: string;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableRowsPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_table_api_v1_jobs__job_id__artifacts__artifact_id__table_excel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TableExcelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_job_api_v1_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    job_events_api_v1_jobs__job_id__events_get: {
        parameters: {
            query?: {
                after_sequence?: number;
            };
            header?: {
                "Last-Event-ID"?: string | null;
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_job_execution_trace_api_v1_jobs__job_id__execution_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobExecutionTraceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_annotation_api_v1_knowledge_annotations__annotation_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                annotation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_annotation_api_v1_knowledge_annotations__annotation_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                annotation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeAnnotationUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeAnnotationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_knowledge_status_api_v1_knowledge_data_sources__data_source_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeStatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_get: {
        parameters: {
            query?: {
                scope_type?: ("datasource" | "table" | "column" | "metric") | null;
                scope_key?: string | null;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeAnnotationResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_annotation_api_v1_knowledge_data_sources__data_source_id__annotations_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeAnnotationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeAnnotationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_export_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_import_post: {
        parameters: {
            query?: {
                on_duplicate?: "skip" | "replace";
                dry_run?: boolean;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_import_annotations_api_v1_knowledge_data_sources__data_source_id__annotations_import_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeImportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_documents_api_v1_knowledge_data_sources__data_source_id__documents_get: {
        parameters: {
            query?: {
                document_type?: ("index" | "table_schema") | null;
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeDocumentSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_document_api_v1_knowledge_data_sources__data_source_id__documents__document_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeDocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_knowledge_api_v1_knowledge_data_sources__data_source_id__generate_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeJobResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_index_api_v1_knowledge_data_sources__data_source_id__index_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeDocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_compact_schema_api_v1_knowledge_data_sources__data_source_id__schema_compact_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompactSchemaResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_table_document_api_v1_knowledge_data_sources__data_source_id__table_get: {
        parameters: {
            query: {
                key: string;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeDocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_versions_api_v1_knowledge_data_sources__data_source_id__versions_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                data_source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeVersionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_connections_api_v1_models_connections_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelConnectionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_connection_api_v1_models_connections_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelConnectionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelConnectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_connection_api_v1_models_connections__connection_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                connection_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelConnectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_connection_api_v1_models_connections__connection_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                connection_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_connection_api_v1_models_connections__connection_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                connection_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelConnectionUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelConnectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_connection_api_v1_models_connections__connection_id__test_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                connection_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelConnectionTestResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_profiles_api_v1_models_profiles_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_profile_api_v1_models_profiles_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelProfileCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_default_profile_api_v1_models_profiles_default_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"] | null;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_profile_api_v1_models_profiles__profile_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_profile_api_v1_models_profiles__profile_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_profile_api_v1_models_profiles__profile_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelProfileUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_default_profile_api_v1_models_profiles__profile_id__default_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    operational_status_api_v1_ops_status_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_organizations_api_v1_organizations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationResponse"][];
                };
            };
        };
    };
    current_organization_api_v1_organizations_current_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_organization_api_v1_organizations__organization_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                organization_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    connections_api_v1_power_bi_connections_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConnectionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    connect_api_v1_power_bi_connections_start_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConnectionStart"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    disconnect_api_v1_power_bi_connections__connection_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                connection_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    features_api_v1_power_bi_features_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PowerBIFeatures"];
                };
            };
        };
    };
    discover_api_v1_power_bi_reports_discover_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReportLookup"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    }[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_api_v1_power_bi_reports_resolve_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReportLookup"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportCandidate"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    embed_api_v1_power_bi_reports__binding_id__embed_config_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Organization-ID"?: string | null;
            };
            path: {
                binding_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EmbedConfiguration"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    readiness_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
