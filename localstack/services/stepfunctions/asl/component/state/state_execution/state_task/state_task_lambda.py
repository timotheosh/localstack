from botocore.exceptions import ClientError

from localstack.aws.api.lambda_ import InvocationRequest, InvocationType
from localstack.aws.api.stepfunctions import (
    HistoryEventExecutionDataDetails,
    HistoryEventType,
    LambdaFunctionFailedEventDetails,
    LambdaFunctionScheduledEventDetails,
    LambdaFunctionSucceededEventDetails,
)
from localstack.services.stepfunctions.asl.component.common.error_name.custom_error_name import (
    CustomErrorName,
)
from localstack.services.stepfunctions.asl.component.common.error_name.failure_event import (
    FailureEvent,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name import (
    StatesErrorName,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name_type import (
    StatesErrorNameType,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task import (
    lambda_eval_utils,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.service.resource import (
    LambdaResource,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.state_task import (
    StateTask,
)
from localstack.services.stepfunctions.asl.eval.environment import Environment
from localstack.services.stepfunctions.asl.eval.event.event_detail import EventDetails
from localstack.services.stepfunctions.asl.utils.encoding import to_json_str


class StateTaskLambda(StateTask):
    resource: LambdaResource

    def _from_error(self, env: Environment, ex: Exception) -> FailureEvent:
        error = "Exception"
        if isinstance(ex, lambda_eval_utils.LambdaFunctionErrorException):
            error_name = CustomErrorName(error)
            cause = ex.payload
        elif isinstance(ex, ClientError):
            error_name = CustomErrorName(error)
            cause = ex.response["Error"]["Message"]
        else:
            error_name = StatesErrorName(StatesErrorNameType.StatesTaskFailed)
            cause = str(ex)

        return FailureEvent(
            error_name=error_name,
            event_type=HistoryEventType.LambdaFunctionFailed,
            event_details=EventDetails(
                lambdaFunctionFailedEventDetails=LambdaFunctionFailedEventDetails(
                    error=error,
                    cause=cause,
                )
            ),
        )

    def _eval_parameters(self, env: Environment) -> dict:
        env_state_input = env.stack.pop()
        parameters = InvocationRequest(
            FunctionName=self.resource.resource_arn,
            InvocationType=InvocationType.RequestResponse,
            Payload=env_state_input,
        )

        explicit_parameters = super()._eval_parameters(env=env)
        parameters.update(explicit_parameters)

        return parameters

    def _eval_execution(self, env: Environment) -> None:
        env.event_history.add_event(
            hist_type_event=HistoryEventType.LambdaFunctionScheduled,
            event_detail=EventDetails(
                lambdaFunctionScheduledEventDetails=LambdaFunctionScheduledEventDetails(
                    resource=self.resource.resource_arn,
                    input=to_json_str(env.inp),
                    inputDetails=HistoryEventExecutionDataDetails(
                        truncated=False  # Always False for api calls.
                    ),
                )
            ),
        )
        env.event_history.add_event(
            hist_type_event=HistoryEventType.LambdaFunctionStarted,
            event_detail=EventDetails(),
        )

        parameters = self._eval_parameters(env=env)
        if "Payload" in parameters:
            parameters["Payload"] = lambda_eval_utils.to_payload_type(parameters["Payload"])

        lambda_eval_utils.exec_lambda_function(env=env, parameters=parameters)

        # In lambda invocations, only payload is passed on as output.
        output = env.stack.pop()
        output_payload = output["Payload"]
        env.stack.append(output_payload)

        env.event_history.add_event(
            hist_type_event=HistoryEventType.LambdaFunctionSucceeded,
            event_detail=EventDetails(
                lambdaFunctionSucceededEventDetails=LambdaFunctionSucceededEventDetails(
                    output=to_json_str(output_payload),
                    outputDetails=HistoryEventExecutionDataDetails(
                        truncated=False  # Always False for api calls.
                    ),
                )
            ),
        )
