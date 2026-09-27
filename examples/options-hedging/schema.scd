{
	"name": "OptionsHedgingMemory",
	"version": "2.0",
	"spaces": [],
	"entities": [
		{
			"name": "ObjectRoot",
			"attributes": [
				{"name": "rightToDelete"}
			],
			"entities": [
				{
					"name": "RetiQoLease",
					"attributes": [
						{"name": "id"},
						{"name": "app_id"},
						{"name": "execution_id"},
						{"name": "issued_to"},
						{"name": "intent"},
						{"name": "consensus_id"},
						{"name": "scope_hash"},
						{"name": "expires_at"},
						{"name": "issued_at"},
						{"name": "nonce"},
						{"name": "version"},
						{"name": "signature"}
					]
				},
				{
					"name": "HedgeOrder",
					"attributes": [
						{"name": "orderId"},
						{"name": "decisionId"},
						{"name": "underlying"},
						{"name": "structure"},
						{"name": "expiry"},
						{"name": "contracts"},
						{"name": "status"}
					]
				},
				{
					"name": "Decision",
					"attributes": [
						{"name": "decisionId"},
						{"name": "workflow"},
						{"name": "subject"},
						{"name": "proposal"},
						{"name": "proposedBy"},
						{"name": "rationale"},
						{"name": "alternatives"},
						{"name": "status"},
						{"name": "version"},
						{"name": "terms"},
						{"name": "appliedLessons"}
					]
				},
				{
					"name": "Review",
					"attributes": [
						{"name": "reviewId"},
						{"name": "decisionId"},
						{"name": "version"},
						{"name": "reviewer"},
						{"name": "role"},
						{"name": "verdict"},
						{"name": "note"}
					]
				},
				{
					"name": "Objection",
					"attributes": [
						{"name": "objectionId"},
						{"name": "decisionId"},
						{"name": "version"},
						{"name": "raisedBy"},
						{"name": "check"},
						{"name": "reason"},
						{"name": "blocking"},
						{"name": "status"},
						{"name": "resolution"}
					]
				},
				{
					"name": "Outcome",
					"attributes": [
						{"name": "outcomeId"},
						{"name": "decisionId"},
						{"name": "expected"},
						{"name": "observed"},
						{"name": "variance"},
						{"name": "lesson"}
					]
				},
				{
					"name": "Lesson",
					"attributes": [
						{"name": "lessonId"},
						{"name": "workflow"},
						{"name": "check"},
						{"name": "facts"},
						{"name": "summary"},
						{"name": "learnedFrom"},
						{"name": "learnedBy"}
					]
				}
			]
		}
	],
	"interactions": [
		{
			"name": "InteractionRoot",
			"interactions": [
				{
					"name": "RetiQoRequestLease",
					"transport": "trusted",
					"parameters": [
						"app_id",
						"execution_id",
						"intent",
						"consensus_id",
						"requested_scope",
						"issued_to"
					]
				},
				{
					"name": "DecisionProposed",
					"parameters": [
						"decisionId",
						"subject",
						"version"
					]
				},
				{
					"name": "ReviewSubmitted",
					"parameters": [
						"decisionId",
						"reviewer",
						"verdict"
					]
				},
				{
					"name": "ObjectionRaised",
					"parameters": [
						"decisionId",
						"objectionId",
						"blocking"
					]
				},
				{
					"name": "DecisionFinalized",
					"parameters": [
						"decisionId",
						"status"
					]
				},
				{
					"name": "OutcomeRecorded",
					"parameters": [
						"decisionId",
						"outcomeId"
					]
				},
				{
					"name": "LessonRecorded",
					"parameters": [
						"lessonId",
						"check"
					]
				},
				{
					"name": "AgentMessage",
					"parameters": [
						"fromAgent",
						"toAgent",
						"decisionId",
						"kind",
						"text"
					]
				}
			]
		}
	]
}
